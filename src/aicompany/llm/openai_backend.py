"""Live-Backend auf Basis des OpenAI Agents SDK (openai-agents 0.24.0).

Jeder Agentenaufruf erzeugt einen `agents.Agent` mit strukturiertem `output_type`,
begrenzten Ausgabe-Tokens und nur den von der Sicherheitsrichtlinie freigegebenen Werkzeugen.
Es werden KEINE Shell-, Computer- oder Code-Interpreter-Werkzeuge vergeben.
"""
from __future__ import annotations

import asyncio

from ..budget import CallUsage
from .base import AgentCall, AgentCallResult, LLMFatalError, LLMOutputError, LLMTransientError


class OpenAIAgentsBackend:
    name = "openai-agents"
    simulated = False

    def __init__(self, *, api_key: str, disable_tracing: bool = True, timeout_seconds: int = 180):
        if not api_key:
            raise LLMFatalError("OPENAI_API_KEY fehlt")
        import agents  # Import erst hier, damit Dry-Run ohne Netzwerkzugriff funktioniert

        agents.set_default_openai_key(api_key, use_for_tracing=not disable_tracing)
        if disable_tracing:
            agents.set_tracing_disabled(True)
        self._agents = agents
        self.timeout = timeout_seconds

    def _build_agent(self, call: AgentCall):
        a = self._agents
        tools = []
        if "web_search" in call.tools:
            tools.append(a.WebSearchTool(search_context_size="medium"))
        return a.Agent(
            name=call.agent_id,
            instructions=call.instructions,
            model=call.model,
            model_settings=a.ModelSettings(max_tokens=call.max_output_tokens, parallel_tool_calls=False),
            output_type=call.output_type,
            tools=tools,
        )

    async def run(self, call: AgentCall) -> AgentCallResult:
        import openai

        a = self._agents
        agent = self._build_agent(call)
        try:
            result = await asyncio.wait_for(
                a.Runner.run(agent, call.prompt, max_turns=6 if call.tools else 2), timeout=self.timeout
            )
        except asyncio.TimeoutError as exc:
            raise LLMTransientError(f"Zeitüberschreitung nach {self.timeout}s") from exc
        except (openai.RateLimitError, openai.APIConnectionError, openai.APITimeoutError, openai.InternalServerError) as exc:
            raise LLMTransientError(f"{type(exc).__name__}: {exc}") from exc
        except (openai.AuthenticationError, openai.PermissionDeniedError, openai.NotFoundError, openai.BadRequestError) as exc:
            raise LLMFatalError(f"{type(exc).__name__}: {exc}") from exc
        except a.ModelBehaviorError as exc:
            raise LLMOutputError(str(exc)) from exc
        except a.MaxTurnsExceeded as exc:
            raise LLMOutputError(f"Maximale Zugzahl überschritten: {exc}") from exc

        output = result.final_output
        if not isinstance(output, call.output_type):
            raise LLMOutputError(f"Unerwarteter Ausgabetyp {type(output).__name__}")

        web_calls, urls = 0, []
        for item in result.new_items:
            raw = getattr(item, "raw_item", None)
            if getattr(raw, "type", None) == "web_search_call":
                web_calls += 1
                action = getattr(raw, "action", None)
                for src in getattr(action, "sources", None) or []:
                    url = getattr(src, "url", None)
                    if url:
                        urls.append(url)
            for part in getattr(raw, "content", None) or []:
                for ann in getattr(part, "annotations", None) or []:
                    if getattr(ann, "type", None) == "url_citation" and getattr(ann, "url", None):
                        urls.append(ann.url)
        u = result.context_wrapper.usage
        usage = CallUsage(
            input_tokens=u.input_tokens, output_tokens=u.output_tokens, requests=u.requests,
            web_search_calls=web_calls, known=u.requests > 0,
        )
        return AgentCallResult(output=output, usage=usage, model=call.model, simulated=False,
                               cited_urls=sorted(set(urls)), web_search_calls=web_calls)

"""Live-Backend auf Basis des OpenAI Agents SDK (openai-agents 0.24.0).

Jeder Agentenaufruf erzeugt einen `agents.Agent` mit strukturiertem `output_type`,
begrenzten Ausgabe-Tokens und nur den von der Sicherheitsrichtlinie freigegebenen Werkzeugen.
Es werden KEINE Shell-, Computer- oder Code-Interpreter-Werkzeuge vergeben.
"""
from __future__ import annotations

import asyncio

from ..budget import CallUsage
from .base import AgentCall, AgentCallResult, LLMFatalError, LLMOutputError, LLMTransientError


class CostCapReached(Exception):
    """Der laufende Auftrag hat seine Kostenobergrenze erreicht und wurde gestoppt."""


def workbench_tools(agents_mod, wb):
    """Werkzeuge des Software-Teams als SDK-Function-Tools. Fehler gehen als Text an das Modell zurück."""

    def guarded(fn):
        try:
            return fn()
        except Exception as exc:  # Sicherheitsregeln/Pfadfehler → Rückmeldung statt Absturz
            return f"FEHLER: {exc}"

    @agents_mod.function_tool
    def list_files() -> str:
        """Listet alle Dateien des Projekts auf."""
        return guarded(lambda: "\n".join(wb.list_files()) or "(Projekt ist leer)")

    @agents_mod.function_tool
    def read_file(path: str) -> str:
        """Liest eine Projektdatei.

        Args:
            path: Pfad relativ zum Projektordner, z. B. app/main.py
        """
        return guarded(lambda: wb.read_file(path))

    @agents_mod.function_tool
    def write_file(path: str, content: str) -> str:
        """Legt eine Projektdatei an oder überschreibt sie vollständig.

        Args:
            path: Pfad relativ zum Projektordner, z. B. app/main.py oder tests/test_api.py
            content: kompletter neuer Dateiinhalt
        """
        return guarded(lambda: wb.write_file(path, content))

    @agents_mod.function_tool
    def delete_file(path: str) -> str:
        """Löscht eine Projektdatei.

        Args:
            path: Pfad relativ zum Projektordner
        """
        return guarded(lambda: wb.delete_file(path))

    @agents_mod.function_tool
    async def run_tests() -> str:
        """Führt die Tests des Projekts (pytest) isoliert aus und liefert das Ergebnis."""
        def go():
            r = wb.run_tests()
            head = "BESTANDEN" if r.passed else "NICHT BESTANDEN"
            return f"{head}: {r.summary}\n" + "\n".join(r.problems) + "\n" + r.output[-2500:]
        return await asyncio.to_thread(guarded, go)  # blockiert den Orchestrator (Heartbeat/Stopp) nicht

    return [list_files, read_file, write_file, delete_file, run_tests]


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
        if call.workbench is not None:
            tools.extend(workbench_tools(a, call.workbench))
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
        hooks = None
        if call.cost_cap_eur is not None and call.cost_fn is not None:
            spent = {"eur": 0.0}

            class CostGuard(a.RunHooks):
                async def on_llm_end(self, context, agent, response):  # noqa: ARG002
                    u = response.usage
                    spent["eur"] += call.cost_fn(call.model, u.input_tokens, u.output_tokens)
                    if spent["eur"] > call.cost_cap_eur:
                        raise CostCapReached(f"Kostenobergrenze {call.cost_cap_eur:.3f} € erreicht ({spent['eur']:.3f} €)")

            hooks = CostGuard()
        max_turns = call.max_turns or (6 if call.tools else 2)
        timeout = self.timeout * (4 if call.workbench is not None else 1)
        try:
            result = await asyncio.wait_for(a.Runner.run(agent, call.prompt, max_turns=max_turns, hooks=hooks), timeout=timeout)
        except CostCapReached as exc:
            raise LLMOutputError(f"Auftrag abgebrochen: {exc}") from exc
        except asyncio.TimeoutError as exc:
            raise LLMTransientError(f"Zeitüberschreitung nach {timeout}s") from exc
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

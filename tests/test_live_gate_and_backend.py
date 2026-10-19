"""Live-Modus-Sperre und OpenAI-Agents-Backend (ohne Netzwerk, mit Attrappe)."""
import asyncio
from types import SimpleNamespace

import pytest

from aicompany import preflight
from aicompany.agents import schemas as S
from aicompany.config import load_settings
from aicompany.llm.base import AgentCall, LLMFatalError, LLMOutputError, LLMTransientError


def test_live_mode_blocked_without_selftest_and_key(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(preflight, "MARKER", tmp_path / "none.json")
    s = load_settings(mode="live", data_dir=tmp_path / "live")
    problems = preflight.live_readiness(s)
    assert any("selftest" in p for p in problems) and any("OPENAI_API_KEY" in p for p in problems)
    from aicompany.company import make_backend
    with pytest.raises(preflight.PreflightError):
        make_backend(s)


def test_live_mode_requires_current_code(monkeypatch, tmp_path):
    marker = tmp_path / "m.json"
    marker.write_text('{"passed": true, "code_hash": "veraltet"}')
    monkeypatch.setattr(preflight, "MARKER", marker)
    assert preflight.selftest_status()["passed"] is False


def test_unpriced_model_blocks_live(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-xxxxxxxxxxxxxxxxxxxx")
    marker = tmp_path / "m.json"
    marker.write_text('{"passed": true, "code_hash": "%s"}' % preflight.code_hash())
    monkeypatch.setattr(preflight, "MARKER", marker)
    s = load_settings(mode="live", data_dir=tmp_path / "l2", overrides={"models": {"default": "unbekanntes-modell"}})
    assert any("Keine Preise" in p for p in preflight.live_readiness(s))
    s_ok = load_settings(mode="live", data_dir=tmp_path / "l3")
    assert preflight.live_readiness(s_ok) == []


def _call(tools=()):
    return AgentCall(agent_id="qa", task_id="T-1", task_key="k", kind="qa_review", instructions="i", prompt="p",
                     output_type=S.QAReview, model="gpt-5.4-mini", max_output_tokens=500, tools=list(tools))


def _backend(monkeypatch, behaviour):
    from aicompany.llm import openai_backend
    b = openai_backend.OpenAIAgentsBackend(api_key="sk-test-xxxxxxxxxxxxxxxxxxxx")

    async def fake_run(agent, prompt, max_turns, **kw):
        return behaviour(agent)

    monkeypatch.setattr(b._agents.Runner, "run", staticmethod(fake_run))
    return b


def test_openai_backend_parses_usage_and_citations(monkeypatch):
    review = S.QAReview(verdict="pass", summary="ok", issues=[], unsupported_claims=[], compliance_risks=[], approvals_required=[])

    def ok(agent):
        assert agent.output_type is S.QAReview and agent.model_settings.max_tokens == 500
        assert agent.tools and type(agent.tools[0]).__name__ == "WebSearchTool"
        search = SimpleNamespace(raw_item=SimpleNamespace(type="web_search_call", action=SimpleNamespace(
            sources=[SimpleNamespace(url="https://a.example/x")])))
        msg = SimpleNamespace(raw_item=SimpleNamespace(type="message", content=[SimpleNamespace(annotations=[
            SimpleNamespace(type="url_citation", url="https://b.example/y")])]))
        usage = SimpleNamespace(input_tokens=1200, output_tokens=300, requests=2)
        return SimpleNamespace(final_output=review, new_items=[search, msg], context_wrapper=SimpleNamespace(usage=usage))

    b = _backend(monkeypatch, ok)
    res = asyncio.run(b.run(_call(tools=["web_search"])))
    assert res.output == review and not res.simulated
    assert res.usage.input_tokens == 1200 and res.usage.web_search_calls == 1
    assert res.cited_urls == ["https://a.example/x", "https://b.example/y"]


def test_openai_backend_maps_errors(monkeypatch):
    from agents import ModelBehaviorError

    def bad(agent):
        raise ModelBehaviorError("invalid json")

    with pytest.raises(LLMOutputError):
        asyncio.run(_backend(monkeypatch, bad).run(_call()))

    def wrong_type(agent):
        return SimpleNamespace(final_output="text", new_items=[], context_wrapper=SimpleNamespace(usage=None))

    with pytest.raises(LLMOutputError):
        asyncio.run(_backend(monkeypatch, wrong_type).run(_call()))

    def timeout(agent):
        raise asyncio.TimeoutError()

    with pytest.raises(LLMTransientError):
        asyncio.run(_backend(monkeypatch, timeout).run(_call()))


def test_openai_backend_requires_key():
    from aicompany.llm.openai_backend import OpenAIAgentsBackend
    with pytest.raises(LLMFatalError):
        OpenAIAgentsBackend(api_key="")


def test_no_dangerous_tools_given(monkeypatch):
    from aicompany.llm.openai_backend import OpenAIAgentsBackend
    b = OpenAIAgentsBackend(api_key="sk-test-xxxxxxxxxxxxxxxxxxxx")
    agent = b._build_agent(_call(tools=["web_search", "workspace_write", "shell_exec"]))
    assert [type(t).__name__ for t in agent.tools] == ["WebSearchTool"]

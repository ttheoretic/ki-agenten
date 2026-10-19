"""Software-Team: Werkbank, Codeprüfung, isolierte Tests, Entwicklungsablauf, Live-Werkzeuge."""
import asyncio

import pytest

from aicompany.checks import scan_python
from aicompany.llm.mock import MockBackend, _webapp_files
from aicompany.security import PermissionDenied
from aicompany.workbench import Workbench

from conftest import run, run_until_finished


@pytest.fixture
def wb(company):
    return Workbench(company.sandbox, "builder", "product", company.redactor, mode="subprocess", timeout=60)


@pytest.mark.parametrize("code", [
    "import subprocess", "from socket import socket", "import requests", "import os\nos.system('ls')",
    "eval('1')", "import ctypes", "open('/etc/passwd')", "import importlib", "x = __import__('os')",
])
def test_scanner_rejects_dangerous_code(code):
    assert scan_python(code, "x.py")


def test_scanner_accepts_normal_app_code():
    for path, content in _webapp_files(validation=True, export=True, vat_bug=False).items():
        if path.endswith(".py"):
            assert scan_python(content, path) == [], path


def test_workbench_rejects_bad_files(wb):
    with pytest.raises(PermissionDenied):
        wb.write_file("../escape.py", "x = 1")
    with pytest.raises(PermissionDenied):
        wb.write_file("app/run.sh", "rm -rf /")
    with pytest.raises(PermissionDenied):
        wb.write_file("app/evil.py", "import subprocess")
    with pytest.raises(PermissionDenied):
        wb.write_file("requirements.txt", "requests==2.0\n")
    assert wb.list_files() == []


def test_tests_run_isolated_and_report_failures(wb, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-never-leak-1234567890")
    for p, c in _webapp_files(validation=False, export=False, vat_bug=True).items():
        wb.write_file(p, c)
    wb.write_file("tests/test_env.py", "import os\n\ndef test_no_secrets():\n    assert 'OPENAI_API_KEY' not in os.environ\n")
    r = wb.run_tests()
    assert r.executed and not r.passed and "1 failed" in r.summary  # absichtlicher MwSt-Fehler
    for p, c in _webapp_files(validation=False, export=False, vat_bug=False).items():
        wb.write_file(p, c)
    r = wb.run_tests()
    assert r.passed, r.output  # inkl. Test: keine Schlüssel in der Testumgebung


def test_infinite_loop_is_stopped(company):
    wb = Workbench(company.sandbox, "builder", "product", company.redactor, mode="subprocess", timeout=10)
    wb.write_file("tests/test_loop.py", "def test_forever():\n    while True:\n        pass\n")
    r = wb.run_tests()
    assert not r.passed and ("Zeitüberschreitung" in r.summary or "failed" in r.summary or "Exitcode" in r.summary)


def test_execution_can_be_disabled(company):
    wb = Workbench(company.sandbox, "builder", "product", company.redactor, mode="off")
    wb.write_file("tests/test_a.py", "def test_a():\n    assert True\n")
    r = wb.run_tests()
    assert not r.executed and "deaktiviert" in r.summary


def test_full_development_flow(company):
    run(company)
    design = company.tasks.get_by_key("p2.builder.design")
    impl = company.tasks.get_by_key("p2.builder.product")
    assert design.status == "completed" and design.kind == "tech_design"
    assert impl.kind == "implement" and impl.status == "completed"
    tr = impl.result["derived"]["test_run"]
    assert tr["executed"] and tr["passed"]
    assert impl.result["derived"]["test_runs_during_work"] >= 2  # Fehler gefunden und behoben
    assert impl.revision_count == 1  # QA-Code-Review hat die erste Version zurückgegeben
    files = (company.settings.workspace_dir / "product")
    assert (files / "app" / "main.py").exists() and (files / "Dockerfile").exists()
    assert "negative" in (files / "tests" / "test_api.py").read_text()  # Korrektur wurde mit Test abgesichert
    assert company.events.list(types=["code.tests_run"])


def test_failing_tests_send_work_back(make_company):
    class Sloppy(MockBackend):
        def _gen_implement(self, call):
            out = super()._gen_implement(call)
            if call.revision == 0:  # lässt einen kaputten Stand zurück
                call.workbench.write_file("tests/test_broken.py", "def test_broken():\n    assert 1 == 2\n")
            else:
                call.workbench.delete_file("tests/test_broken.py")
            return out

    c = make_company(backend=Sloppy())
    run(c)
    impl = c.tasks.get_by_key("p2.builder.product")
    assert any("Tests schlagen fehl" in f["message"] for f in impl.feedback)
    assert impl.status in ("completed", "pending", "review")


def test_qa_receives_code_for_review(make_company):
    seen = {}
    backend = MockBackend()
    original = backend.run

    async def spy(call):
        if call.task_key == "p2.qa.product_test":
            seen["code"] = call.context.get("code")
            seen["test_run"] = call.context.get("test_run")
        return await original(call)

    backend.run = spy
    c = make_company(backend=backend)
    run(c)
    assert "app/main.py" in seen["code"] and seen["test_run"]["passed"]


def test_deploy_app_creates_release_and_needs_owner(company):
    run_until_finished(company, max_runs=2)
    ap = next(a for a in company.approvals.list() if a.action_type == "deploy_app")
    company.approvals.decide(ap.id, "approve", actor="owner", confirmed_hash=ap.params_hash)
    done = company.approvals.execute(ap.id)
    assert done.execution_status == "manual_required"
    assert (company.settings.releases_dir / ap.id / "Dockerfile").exists()


def test_live_builder_gets_workbench_tools_and_cost_guard(company, monkeypatch):
    from types import SimpleNamespace

    from aicompany.agents import schemas as S
    from aicompany.llm.base import AgentCall, LLMOutputError
    from aicompany.llm.openai_backend import OpenAIAgentsBackend

    b = OpenAIAgentsBackend(api_key="sk-test-xxxxxxxxxxxxxxxxxxxx")
    wb = Workbench(company.sandbox, "builder", "product", company.redactor, mode="off")
    call = AgentCall(agent_id="builder", task_id="T", task_key="k", kind="implement", instructions="i", prompt="p",
                     output_type=S.ImplementationReport, model="gpt-5.4-mini", max_output_tokens=500, tools=[],
                     workbench=wb, max_turns=5, cost_cap_eur=0.0001, cost_fn=company.budget.cost_eur)
    agent = b._build_agent(call)
    assert {t.name for t in agent.tools} == {"list_files", "read_file", "write_file", "delete_file", "run_tests"}

    async def fake_run(agent, prompt, max_turns, hooks=None):
        assert max_turns == 5
        usage = SimpleNamespace(input_tokens=1_000_000, output_tokens=0)
        await hooks.on_llm_end(None, agent, SimpleNamespace(usage=usage))  # teure Antwort → Abbruch

    monkeypatch.setattr(b._agents.Runner, "run", staticmethod(fake_run))
    with pytest.raises(LLMOutputError, match="Kostenobergrenze"):
        asyncio.run(b.run(call))

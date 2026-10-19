"""Orchestrierung: vollständiger Zyklus, Wiederaufnahme, Fehler, Überarbeitungen, Zuständigkeiten, Steuerung."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from aicompany.db import now_iso
from aicompany.llm.mock import MockBackend
from aicompany.orchestrator import Orchestrator, RunActive
from aicompany.tasks import TaskSpec, TaskStatus as TS

from conftest import run, run_until_finished


def statuses(c):
    return {t.key: t.status for t in c.tasks.list()}


def test_full_dry_run_cycle_completes(company):
    summaries = run_until_finished(company)
    assert company.clock.cycle() == 2  # das Unternehmen läuft weiter: nächster Zyklus automatisch geplant
    st = {t.key: t.status for t in company.tasks.list(cycle=1)}
    assert all(v == TS.COMPLETED for v in st.values()), st
    assert all(s.agent_calls <= 20 for s in summaries)
    # Idee anhand dokumentierter Kriterien ausgewählt
    sel = company.db.get_meta("selected_idea")
    assert sel and "angebotsrechner-handwerk" in sel
    evaluation = company.tasks.get_by_key("p1.strategy.evaluate").result["derived"]["scorecards"]
    assert len(evaluation) == 5 and evaluation[0]["total"] >= evaluation[-1]["total"]
    # QA hat den ersten MVP-Build zurückgegeben, CEO die Positionierung
    assert company.tasks.get_by_key("p2.builder.product").revision_count == 1
    assert company.tasks.get_by_key("p3.marketing.positioning").revision_count == 1
    fb = [e for e in company.events.list(types=["comm.feedback"])]
    assert {(e.from_agent, e.to_agent) for e in fb} >= {("qa", "builder"), ("ceo", "marketing")}
    # Externe Aktionen nur als Freigabeantrag
    aps = company.approvals.list()
    aps = [a for a in aps if company.tasks.get(a.task_id).cycle == 1]
    assert {a.action_type for a in aps} == {"publish_website", "publish_content", "paid_ads"}
    assert all(a.status == "pending" and a.execution_status == "not_started" for a in aps)
    # Dateien im Workspace erzeugt
    assert (company.settings.workspace_dir / "product" / "index.html").exists()
    assert (company.settings.workspace_dir / "site" / "impressum.html").exists()
    # Meilensteine und Berichte
    assert len([e for e in company.events.list(types=["milestone.achieved"]) if "Zyklus 1" in e.message]) == 5
    assert company.db.query("SELECT * FROM artifacts WHERE kind='report'")


def test_all_agents_participate(company):
    run_until_finished(company)
    agents = {r["agent"] for r in company.db.query("SELECT DISTINCT agent FROM cost_records")}
    assert agents == {"ceo", "research", "strategy", "finance", "product", "builder", "marketing", "sales",
                      "operations", "qa", "analytics"}


def test_resume_after_crash(company):
    run(company)  # erster Lauf
    t = company.tasks.ready(current_day=30, paused_agents=set())[0]
    # Absturz simulieren: Aufgabe von einem Lauf übernommen, dessen Heartbeat veraltet ist
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    company.db.execute("INSERT INTO runs(id, started_at, status, mode, trigger, heartbeat_at) VALUES ('R-dead', ?, 'running', 'dry_run', 'x', ?)",
                       (old, old))
    assert company.tasks.claim(t.id, "R-dead")
    s = run(company)
    assert company.db.query_one("SELECT status FROM runs WHERE id='R-dead'")["status"] == "crashed"
    assert company.events.list(types=["task.recovered"])
    assert company.tasks.get(t.id).status != TS.IN_PROGRESS
    assert s.status == "completed"


def test_parallel_runs_are_locked(company):
    company.db.execute("INSERT INTO runs(id, started_at, status, mode, trigger, heartbeat_at) VALUES ('R-live', ?, 'running', 'dry_run', 'x', ?)",
                       (now_iso(), now_iso()))
    with pytest.raises(RunActive):
        asyncio.run(Orchestrator(company).run_once())


def test_transient_api_errors_are_retried(make_company):
    backend = MockBackend(fail_plan={"p1.research.opportunities": 1})
    c = make_company(backend=backend, budget={"max_agent_calls_per_run": 3})
    run(c)
    assert c.tasks.get_by_key("p1.research.opportunities").status == TS.COMPLETED
    assert len(c.events.list(types=["api.error"])) == 1
    assert backend.calls.count("p1.research.opportunities") == 2


def test_api_outage_stops_run_and_keeps_task(make_company):
    backend = MockBackend(fail_plan={"p1.research.opportunities": 10})
    c = make_company(backend=backend)
    s = run(c)
    assert "API nicht erreichbar" in s.stop_reason
    t = c.tasks.get_by_key("p1.research.opportunities")
    assert t.status == TS.PENDING and t.error
    assert s.agent_calls == c.settings.budget.max_attempts_per_call
    # Nach Wiederherstellung läuft es weiter
    backend.fail_plan.clear()
    run(c)
    assert c.tasks.get_by_key("p1.research.opportunities").status == TS.COMPLETED


def test_invalid_output_goes_to_revision(make_company):
    c = make_company(backend=MockBackend(invalid_plan={"p1.research.opportunities": 1}))
    run(c)
    t = c.tasks.get_by_key("p1.research.opportunities")
    assert t.status == TS.COMPLETED and t.revision_count == 1
    assert c.events.list(types=["agent.output_invalid"])


def test_semantically_invalid_output_rejected(make_company):
    c = make_company(backend=MockBackend(semantic_invalid_plan={"p1.research.opportunities": 1}))
    run(c)
    t = c.tasks.get_by_key("p1.research.opportunities")
    assert t.revision_count == 1
    assert any("Fakt ohne Quelle" in f["message"] for f in t.feedback)


def test_revision_limit_fails_and_blocks_dependents(make_company):
    c = make_company(backend=MockBackend(invalid_plan={"p1.research.opportunities": 99}))
    s = run(c)
    t = c.tasks.get_by_key("p1.research.opportunities")
    assert t.status == TS.FAILED
    assert t.revision_count == c.settings.budget.max_revisions_per_task
    assert c.tasks.get_by_key("p1.strategy.evaluate").status == TS.BLOCKED
    assert "Blockiert" in s.stop_reason
    assert any(e.to_agent == "ceo" for e in c.events.list(types=["comm.message"]))
    # Kein Endlos-Retry: weiterer Lauf macht keine Aufrufe
    assert run(c).agent_calls == 0


def test_selection_rules_override_ceo(make_company):
    c = make_company(experiment={"min_idea_score": 99})
    run(c)
    sel = c.tasks.get_by_key("p1.ceo.select_idea")
    assert c.db.get_meta("selected_idea") is None
    assert sel.status in (TS.PENDING, TS.FAILED)
    assert c.events.list(types=["ceo.decision_blocked"])
    run(c)
    assert c.tasks.get_by_key("p1.ceo.select_idea").status == TS.FAILED
    assert c.tasks.get_by_key("p2.product.mvp_spec").status == TS.BLOCKED


def test_ceo_cannot_execute_specialist_task(company):
    company.tasks.create(TaskSpec(key="x.ceo.research", agent="ceo", kind="market_research", title="CEO recherchiert selbst",
                                  goal="g", description="d", phase=1, output_format="market_research", priority=100))
    company.db.set_meta("workflow_seeded", "1")
    company.clock.start()
    run(company)
    t = company.tasks.get_by_key("x.ceo.research")
    assert t.status == TS.FAILED and "nicht zuständig" in t.error


def test_build_path_traversal_rejected(make_company):
    c2 = make_company(backend=MockBackend(semantic_invalid_plan={"p2.builder.product": 1}))
    for _ in range(3):
        run(c2)
    assert c2.events.list(types=["security.violation"])
    assert c2.tasks.get_by_key("p2.builder.product").revision_count >= 1
    assert not (c2.settings.data_dir / "escape.sh").exists()
    assert not (c2.settings.workspace_dir / "escape.sh").exists()


def test_fabricated_metrics_rejected(make_company):
    c = make_company(backend=MockBackend(semantic_invalid_plan={"p4.analytics.measurement": 1}))
    run_until_finished(c)
    t = c.tasks.get_by_key("p4.analytics.measurement")
    assert any("existiert nicht in den Messdaten" in f["message"] for f in t.feedback)
    assert t.result["output"]["metrics_used"] == []


def test_real_metrics_reach_analytics(company):
    company.db.execute("INSERT INTO metrics(ts, name, value, unit, source) VALUES (?, 'visitors', 120, '', 'manual')", (now_iso(),))
    run_until_finished(company)
    out = company.tasks.get_by_key("p4.analytics.measurement").result["output"]
    assert out["data_available"] is True
    assert out["metrics_used"] == [{"name": "visitors", "value": 120.0, "source": "manual"}]


def test_pause_prevents_dispatch(company):
    company.control.apply("pause", "owner")
    s = run(company)
    assert s.status == "skipped" and s.agent_calls == 0
    company.control.apply("resume", "owner")
    assert run(company).agent_calls > 0


def test_paused_agent_is_skipped(company):
    company.control.set_agent_paused("research", True, "owner")
    s = run(company)
    assert s.agent_calls == 0
    assert "pausierte" in s.stop_reason


def test_stop_cancels_running_calls(make_company):
    c = make_company(backend=MockBackend(delay_seconds=1.5))

    async def scenario():
        job = asyncio.create_task(Orchestrator(c).run_once())
        await asyncio.sleep(0.4)
        c.control.apply("stop", "owner")
        return await job

    s = asyncio.run(scenario())
    assert "Stopp" in s.stop_reason
    assert all(t.status != TS.IN_PROGRESS for t in c.tasks.list())
    assert c.events.list(types=["task.cancelled"])
    assert run(c).status == "skipped"


def test_stop_new_lets_running_finish(make_company):
    c = make_company(backend=MockBackend(delay_seconds=0.6))

    async def scenario():
        job = asyncio.create_task(Orchestrator(c).run_once())
        await asyncio.sleep(0.2)
        c.control.apply("stop_new", "owner")
        return await job

    s = asyncio.run(scenario())
    assert c.tasks.get_by_key("p1.research.opportunities").status == TS.COMPLETED
    assert s.agent_calls == 1
    assert "gestoppt" in s.stop_reason


def test_followup_limit_prevents_loops(make_company):
    from aicompany.agents import schemas as S

    class AlwaysMoreInfo(MockBackend):
        def _gen_ceo_decision(self, call):
            return S.CEODecision(decision="need_more_info", selected_idea_id=None, rationale="mehr Daten", criteria_used=[],
                                 risks_accepted=[], conditions=[], open_questions=[f"Frage {call.revision}"])

    c = make_company(backend=AlwaysMoreInfo())
    for _ in range(4):
        run(c)
    followups = [t for t in c.tasks.list() if t.key.startswith("followup.")]
    assert len(followups) <= c.settings.orchestrator.max_followup_tasks
    assert c.tasks.get_by_key("p1.ceo.select_idea").status == TS.FAILED

"""Dauerbetrieb: Das Unternehmen läuft nach jeder Zyklusentscheidung weiter – Betrieb, Kurswechsel oder neue Nische."""
import json

from aicompany.agents import schemas as S
from aicompany.db import now_iso
from aicompany.llm.mock import MockBackend
from aicompany.scoring import check_selection, score_all
from aicompany.tasks import TaskStatus as TS

from conftest import run, run_until_finished

FIRST_IDEA = "angebotsrechner-handwerk"


def add_metric(c, name, value):
    c.db.execute("INSERT INTO metrics(ts, name, value, unit, source) VALUES (?,?,?,?,?)", (now_iso(), name, value, "", "manual"))


class DecideBackend(MockBackend):
    """Simulation mit fest vorgegebener Zyklusentscheidung."""

    def __init__(self, decision, **kw):
        super().__init__(**kw)
        self.decision = decision

    def _gen_final_decision(self, call):
        return S.FinalDecision(decision=self.decision, rationale="Test", lessons=["Lektion aus Zyklus"], next_steps=["weiter"])


def test_continue_starts_operating_cycle_for_all_departments(company):
    run_until_finished(company)
    assert company.clock.cycle() == 2 and company.clock.cycle_type() == "operate"
    agents = {t.agent for t in company.tasks.list(cycle=2)}
    assert agents >= {"analytics", "product", "builder", "qa", "marketing", "sales", "operations", "finance", "ceo"}
    assert company.events.list(types=["cycle.started"])
    # Betriebszyklus läuft durch und plant danach den nächsten
    run_until_finished(company, cycle=2)
    assert company.clock.cycle() == 3
    assert all(t.status == TS.COMPLETED for t in company.tasks.list(cycle=2) if not t.key.startswith("ceo.review"))
    # neue Produktversion wurde gebaut, getestet und zur Veröffentlichung beantragt
    assert company.tasks.get_by_key("c2.o.builder.update").status == TS.COMPLETED
    assert any(a.task_id == company.tasks.get_by_key("c2.o.ops.release").id for a in company.approvals.list())
    cycles = json.loads(company.db.get_meta("cycles"))
    assert [c["type"] for c in cycles] == ["launch", "operate", "operate"]
    assert cycles[0]["decision"] == "continue"


def test_failed_niche_triggers_pivot_to_next_idea(company):
    # Echte (hier: eingetragene) Marktdaten: viel Reichweite, keine Käufe → Nische trägt nicht
    run(company)  # Idee wird ausgewählt
    assert json.loads(company.db.get_meta("selected_idea"))["id"] == FIRST_IDEA
    add_metric(company, "visitors", 420)
    add_metric(company, "sales", 0)
    run_until_finished(company)
    assert company.clock.cycle_type() == "pivot"
    assert json.loads(company.db.get_meta("tried_ideas")) == [FIRST_IDEA]
    assert company.tasks.get_by_key("c2.p1.research.opportunities") is None  # keine neue Grundrecherche
    run(company)
    new_idea = json.loads(company.db.get_meta("selected_idea"))
    assert new_idea["id"] != FIRST_IDEA
    assert company.db.query_one("SELECT status FROM ideas WHERE id=?", (FIRST_IDEA,))["status"] == "tried"
    decisions = [d["summary"] for d in company.db.query("SELECT summary FROM decisions")]
    assert any("Kurswechsel" in d for d in decisions)


def test_stop_starts_new_niche_research_with_exclusions(make_company):
    c = make_company(backend=DecideBackend("stop"))
    run_until_finished(c)
    assert c.clock.cycle() == 2 and c.clock.cycle_type() == "launch"
    research = c.tasks.get_by_key("c2.p1.research.opportunities")
    assert research is not None and research.inputs["lessons"]["previous_decision"] == "stop"
    run(c)
    assert json.loads(c.db.get_meta("selected_idea"))["id"] != FIRST_IDEA


def test_tried_idea_cannot_be_selected_again():
    idea = S.IdeaScore(idea_id="x", name="X", value_proposition="", target_group="", monetization="",
                       criteria=[S.CriterionScore(criterion=k, rating=1, evidence="", confidence="high") for k in S.CRITERIA],
                       platform_dependencies=[], kill_criteria=[], missing_information=[])
    cards = score_all(S.IdeaEvaluation(ideas=[idea], recommendation=S.Recommendation(idea_id="x", reason=""), rejected=[], selection_criteria=[]))
    check = check_selection("x", cards, None, None, 0, excluded=["x"])
    assert not check.allowed and "bereits versucht" in check.reasons[0]


def test_max_cycles_stops_company(make_company):
    c = make_company(experiment={"max_cycles": 1})
    run_until_finished(c)
    assert c.db.get_meta("experiment_status") == "finished"
    assert run(c).status == "skipped"


def test_company_memory_reaches_agents(make_company):
    backend = DecideBackend("pivot")
    seen = []
    original = backend.run

    async def spy(call):
        seen.append(call.context.get("company_memory"))
        return await original(call)

    backend.run = spy
    c = make_company(backend=backend)
    run_until_finished(c)
    run(c)
    assert any(m and m["tried_ideas"] == [FIRST_IDEA] for m in seen)


def test_metrics_of_old_idea_do_not_count_for_new_cycle(company):
    run(company)
    add_metric(company, "visitors", 420)
    add_metric(company, "sales", 0)
    run_until_finished(company)
    assert company.clock.cycle_type() == "pivot"
    from aicompany.orchestrator import Orchestrator
    assert Orchestrator(company)._metrics() == []

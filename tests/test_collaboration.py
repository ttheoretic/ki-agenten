"""Teamarbeit: Hilfeanfragen, Warten auf Kollegen, Hilfsangebote bei Rückgaben, Grenzen."""
from aicompany.agents import schemas as S
from aicompany.llm.mock import MockBackend
from aicompany.tasks import TaskStatus as TS

from conftest import run, run_until_finished


def comm(c, t):
    return c.events.list(types=[t], limit=500)


def test_blocking_help_request_waits_for_colleague(company):
    run(company)
    pos = company.tasks.get_by_key("p3.marketing.positioning")
    help_task = [t for t in company.tasks.list() if t.key.startswith("help.p3.marketing.positioning.finance")][0]
    assert help_task.agent == "finance" and help_task.status == TS.COMPLETED
    assert help_task.key in pos.depends_on
    assert any(e.from_agent == "marketing" and e.to_agent == "finance" for e in comm(company, "comm.help_request"))
    assert any(e.from_agent == "finance" and e.to_agent == "marketing" for e in comm(company, "comm.help_answer"))
    assert company.events.list(types=["task.waiting_help"])
    # Wartezeit erhöht nicht die Überarbeitungszahl (nur die CEO-Rückgabe zählt)
    assert pos.revision_count == 1


def test_answers_reach_requester_as_team_notes(make_company):
    seen = {}
    backend = MockBackend()
    original = backend.run

    async def spy(call):
        if call.task_key == "p3.marketing.positioning":
            seen.setdefault("notes", []).append(call.context.get("team_notes"))
        return await original(call)

    backend.run = spy
    c = make_company(backend=backend)
    run(c)
    assert seen["notes"][0] is None  # erster Versuch: noch keine Antwort
    assert any(n and n[0]["from"] == "finance" and n[0]["answer"] for n in seen["notes"][1:])


def test_colleague_offers_help_on_revision(company):
    run(company)
    offers = comm(company, "comm.help_offer")
    # QA gibt den Build zurück → Product bietet Forge Hilfe an (nicht QA selbst)
    assert any(e.from_agent == "product" and e.to_agent == "builder" for e in offers)
    build = company.tasks.get_by_key("p2.builder.product")
    assert any(d.startswith("help.p2.builder.product.product") for d in build.depends_on)


def test_help_limit_per_run(make_company):
    c = make_company(collaboration={"max_consultations_per_run": 1})
    run(c)
    helps = [t for t in c.tasks.list() if t.kind == "consultation"]
    assert len(helps) == 1
    assert c.events.list(types=["collab.limit"])


def test_collaboration_can_be_disabled(make_company):
    c = make_company(collaboration={"enabled": False})
    run_until_finished(c)
    assert not [t for t in c.tasks.list() if t.kind == "consultation"]
    assert c.clock.cycle() == 2


def test_failed_help_does_not_block_requester(make_company):
    class BadHelper(MockBackend):
        def _gen_consultation(self, call):
            return S.Consultation(answer="?", recommendations=[], offers=[], confidence="low")

    c = make_company(backend=BadHelper(), budget={"max_revisions_per_task": 0})
    run(c)
    run(c)
    pos = c.tasks.get_by_key("p3.marketing.positioning")
    assert pos.status != TS.BLOCKED
    assert not any(d.startswith("help.") for d in pos.depends_on if c.tasks.get_by_key(d).status == TS.FAILED)


def test_no_help_from_oneself():
    from aicompany.orchestrator import Orchestrator
    assert all(a not in helpers for a, helpers in Orchestrator.HELPERS.items())

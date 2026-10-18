"""Aufgabenstatus, Übergaben, Duplikatschutz."""
import pytest

from aicompany.tasks import InvalidTransition, TaskSpec, TaskStatus as TS


def spec(key, deps=(), agent="research"):
    return TaskSpec(key=key, agent=agent, kind="market_research", title=key, goal="g", description="d", phase=1,
                    depends_on=list(deps), output_format="market_research")


def test_create_is_idempotent_by_key(company):
    t1, new1 = company.tasks.create(spec("a"))
    t2, new2 = company.tasks.create(spec("a"))
    assert new1 and not new2 and t1.id == t2.id
    assert len(company.tasks.list()) == 1


def test_claim_prevents_double_execution(company):
    t, _ = company.tasks.create(spec("a"))
    assert company.tasks.claim(t.id, "R-1") is True
    assert company.tasks.claim(t.id, "R-2") is False
    assert company.tasks.get(t.id).claimed_by == "R-1"


def test_transitions_enforced(company):
    t, _ = company.tasks.create(spec("a"))
    with pytest.raises(InvalidTransition):
        company.tasks.transition(t.id, TS.COMPLETED, note="skip review")
    company.tasks.claim(t.id, "R-1")
    company.tasks.transition(t.id, TS.REVIEW, note="ok")
    done = company.tasks.transition(t.id, TS.COMPLETED, note="ok")
    assert done.status == TS.COMPLETED and done.completed_at
    assert [h["status"] for h in done.history] == ["pending", "in_progress", "review", "completed"]


def test_ready_respects_dependencies_and_day(company):
    a, _ = company.tasks.create(spec("a"))
    b, _ = company.tasks.create(spec("b", deps=["a"]))
    late = spec("c")
    late.not_before_day = 10
    company.tasks.create(late)
    assert [t.key for t in company.tasks.ready(current_day=1, paused_agents=set())] == ["a"]
    company.tasks.claim(a.id, "R")
    company.tasks.transition(a.id, TS.REVIEW, note="")
    company.tasks.transition(a.id, TS.COMPLETED, note="")
    assert {t.key for t in company.tasks.ready(current_day=10, paused_agents=set())} == {"b", "c"}
    assert company.tasks.ready(current_day=10, paused_agents={"research"}) == []


def test_failed_dependency_blocks_and_retry_unblocks(company):
    a, _ = company.tasks.create(spec("a"))
    b, _ = company.tasks.create(spec("b", deps=["a"]))
    company.tasks.claim(a.id, "R")
    company.tasks.transition(a.id, TS.FAILED, note="x")
    company.tasks.propagate_blocks()
    assert company.tasks.get(b.id).status == TS.BLOCKED
    company.tasks.retry(a.id, "owner")
    assert company.tasks.get(a.id).status == TS.PENDING
    assert company.tasks.get(b.id).status == TS.PENDING


def test_recover_stale_tasks(company):
    a, _ = company.tasks.create(spec("a"))
    company.tasks.claim(a.id, "R-dead")
    recovered = company.tasks.recover_stale({"R-alive"})
    assert [t.id for t in recovered] == [a.id]
    assert company.tasks.get(a.id).status == TS.PENDING
    assert company.events.list(types=["task.recovered"])

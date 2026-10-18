"""Kostenlimits, Warnschwellen und automatischer Stopp."""
from aicompany.budget import BudgetExceeded, CallUsage, RunBudget

from conftest import run


def test_max_agent_calls_per_run_enforced(make_company):
    c = make_company(budget={"max_agent_calls_per_run": 5})
    s = run(c)
    assert s.agent_calls == 5
    assert "Limit von 5 Agentenaufrufen" in s.stop_reason
    assert c.db.query_one("SELECT COUNT(*) n FROM cost_records WHERE run_id=?", (s.run_id,))["n"] == 5


def test_per_run_cost_limit_stops_before_call(make_company):
    c = make_company(budget={"per_run_eur": 0.005})
    s = run(c)
    assert "Laufbudget" in s.stop_reason
    assert s.cost_eur <= 0.005 + 1e-9
    assert c.events.list(types=["budget.blocked"])


def test_monthly_api_budget_hard_stop(make_company):
    c = make_company(budget={"monthly_api_eur": 0.01, "monthly_total_eur": 100})
    s1 = run(c)
    assert "API-Budget" in s1.stop_reason or "ausgeschöpft" in s1.stop_reason
    spent = c.budget.month_spend(("api", "tool"))
    assert spent <= 0.01 + 1e-9
    # Folgelauf startet keine Aufrufe mehr
    s2 = run(c)
    assert s2.agent_calls == 0


def test_warning_thresholds_emitted_once(company):
    b = company.budget
    rb = RunBudget(run_id="R-x")
    limit = company.settings.budget.monthly_api_eur
    for frac in (0.3, 0.55, 0.8, 0.95):  # kumulativ 0.3 -> 0.55 -> ... in Euro-Anteilen
        target = limit * frac - b.month_spend(("api", "tool"))
        company.db.execute("INSERT INTO cost_records(ts, month, kind, cost_eur) VALUES (datetime('now'), ?, 'api', ?)",
                           (b.summary()["month"], target))
        b.check_thresholds()
    b.check_thresholds()  # zweiter Aufruf darf keine Duplikate erzeugen
    warnings = [e for e in company.events.list(types=["comm.message"]) if e.data.get("kind") == "budget.warning"]
    api = sorted(e.data["threshold"] for e in warnings if e.data["scope"] == "api")
    assert api == [0.5, 0.75, 0.9]
    assert all(e.from_agent == "finance" and e.to_agent == "ceo" for e in warnings)
    assert not b.exhausted()
    rb  # noqa


def test_exhaustion_event_and_stop(company):
    b = company.budget
    company.db.execute("INSERT INTO cost_records(ts, month, kind, cost_eur) VALUES (datetime('now'), ?, 'api', ?)",
                       (b.summary()["month"], company.settings.budget.monthly_api_eur))
    b.check_thresholds()
    assert b.exhausted()
    assert company.events.list(types=["budget.exhausted"])
    s = run(company)
    assert s.status == "budget_exhausted" and s.agent_calls == 0


def test_unknown_model_priced_conservatively(company):
    known = company.budget.cost_eur("gpt-5.4-mini", 1_000_000, 1_000_000)
    unknown = company.budget.cost_eur("totally-new-model", 1_000_000, 1_000_000)
    assert unknown > known
    assert company.budget.price("totally-new-model")[1] is False


def test_unknown_usage_recorded_as_estimate(company):
    rb = RunBudget(run_id="R-y")
    company.budget.reserve(rb, "k", 0.02)
    cost = company.budget.record_call(rb, key="k", task_id=None, agent="research", model="mock-model",
                                      usage=CallUsage(known=False), estimate_eur=0.02)
    assert cost == 0.02
    row = company.db.query_one("SELECT estimated FROM cost_records ORDER BY id DESC LIMIT 1")
    assert row["estimated"] == 1


def test_reservations_count_against_limits(company):
    rb = RunBudget(run_id="R-z")
    limit = company.settings.budget.per_run_eur
    company.budget.reserve(rb, "a", limit * 0.6)
    try:
        company.budget.reserve(rb, "b", limit * 0.6)
        raise AssertionError("parallele Reservierung hätte das Laufbudget überschritten")
    except BudgetExceeded as exc:
        assert exc.scope == "run"

"""Bewertungssystem, Finanzrechnung und Ausgabeschemas."""
import pytest
from agents import AgentOutputSchema
from pydantic import ValidationError

from aicompany.agents import schemas as S
from aicompany.agents.roles import ROLES
from aicompany.finance import compute_idea
from aicompany.scoring import WEIGHTS, check_selection, score_idea


def idea(ratings, conf="high"):
    return S.IdeaScore(idea_id="i", name="Idee", value_proposition="v", target_group="t", monetization="m",
                       criteria=[S.CriterionScore(criterion=c, rating=r, evidence="e", confidence=conf) for c, r in ratings.items()],
                       platform_dependencies=[], kill_criteria=[], missing_information=[])


def test_weights_sum_to_100():
    assert sum(WEIGHTS.values()) == 100


def test_score_is_transparent():
    card = score_idea(idea({c: 1.0 for c in S.CRITERIA}))
    assert card.total == 100 and card.complete
    half = score_idea(idea({c: 0.5 for c in S.CRITERIA}, conf="low"))
    assert half.total == pytest.approx(40.0)  # 100 × 0.5 × 0.8
    partial = score_idea(idea({"demand": 1.0}))
    assert not partial.complete and partial.total == 20


def test_selection_requires_reviews_and_minimum():
    card = score_idea(idea({c: 0.9 for c in S.CRITERIA}))
    check = check_selection("i", [card], None, None, 55)
    assert not check.allowed and len(check.reasons) == 2
    fin = S.FinanceAssessment(ideas=[S.IdeaFinance(idea_id="i", pricing_model="one_time", price_eur=10, setup_cost_eur=0,
                                                   monthly_fixed_costs_eur=1, variable_cost_per_sale_eur=0, scenarios=[],
                                                   assumptions=[], budget_risks=[])],
                              recommendation="", unattractive_measures=[], actuals_vs_forecast="keine Ist-Daten")
    qa = S.QAReview(verdict="pass", summary="", issues=[], unsupported_claims=[], compliance_risks=[], approvals_required=[])
    assert check_selection("i", [card], fin, qa, 55).allowed
    crit = qa.model_copy(update={"issues": [S.QAIssue(severity="critical", area="legal", description="Abmahnrisiko",
                                                         suggested_fix="x", suggested_test="y", target_agent="strategy")]})
    assert not check_selection("i", [card], fin, crit, 55).allowed
    assert not check_selection("i", [card], fin, qa, 95).allowed


def test_finance_break_even():
    f = S.IdeaFinance(idea_id="i", pricing_model="one_time", price_eur=29, setup_cost_eur=50, monthly_fixed_costs_eur=8,
                      variable_cost_per_sale_eur=1.6,
                      scenarios=[S.Scenario(name="base", monthly_visitors=400, conversion_rate=0.01, monthly_churn=0)],
                      assumptions=[], budget_risks=[])
    r = compute_idea(f).scenarios[0]
    assert r.monthly_sales == 4 and r.monthly_revenue_eur == 116
    assert r.monthly_profit_eur == pytest.approx(116 - 6.4 - 8)
    assert r.break_even_sales_per_month == 1
    assert r.months_to_recover_setup == pytest.approx(round(50 / 101.6, 1))


@pytest.mark.parametrize("kind", sorted(S.OUTPUT_SCHEMAS))
def test_schemas_strict_compatible(kind):
    AgentOutputSchema(S.OUTPUT_SCHEMAS[kind], strict_json_schema=True).json_schema()


def test_invalid_output_rejected_by_schema():
    with pytest.raises(ValidationError):
        S.CriterionScore(criterion="demand", rating=1.5, evidence="", confidence="high")
    with pytest.raises(ValidationError):
        S.CEODecision.model_validate({"decision": "yolo"})


def test_every_task_kind_has_one_owner():
    from aicompany.workflow import TEMPLATES
    for t in TEMPLATES:
        assert t.kind in ROLES[t.agent].task_kinds, t.key
    assert len(ROLES) == 11

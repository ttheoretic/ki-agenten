"""Deterministische Unit-Economics-Berechnung aus den Annahmen des Finance-Agenten."""
from __future__ import annotations

import math

from pydantic import BaseModel

from .agents.schemas import FinanceAssessment, IdeaFinance


class ScenarioResult(BaseModel):
    name: str
    monthly_sales: float
    monthly_revenue_eur: float
    monthly_variable_costs_eur: float
    monthly_contribution_eur: float
    monthly_profit_eur: float
    margin_pct: float | None
    break_even_sales_per_month: float | None
    months_to_recover_setup: float | None


class IdeaEconomics(BaseModel):
    idea_id: str
    price_eur: float
    pricing_model: str
    scenarios: list[ScenarioResult]
    note: str


def compute_idea(f: IdeaFinance) -> IdeaEconomics:
    results = []
    unit_margin = f.price_eur - f.variable_cost_per_sale_eur
    for s in f.scenarios:
        sales = s.monthly_visitors * s.conversion_rate
        if f.pricing_model == "subscription":
            # Gleichgewichtsbestand bei Abwanderung: Neukunden / Churn (gedeckelt auf 12 Monate Aufbau)
            sales = sales * min(12.0, 1.0 / s.monthly_churn) if s.monthly_churn > 0 else sales * 12
        revenue = sales * f.price_eur
        variable = sales * f.variable_cost_per_sale_eur
        contribution = revenue - variable
        profit = contribution - f.monthly_fixed_costs_eur
        be_sales = (f.monthly_fixed_costs_eur / unit_margin) if unit_margin > 0 else None
        months = (f.setup_cost_eur / profit) if profit > 0 else None
        results.append(ScenarioResult(
            name=s.name,
            monthly_sales=round(sales, 2),
            monthly_revenue_eur=round(revenue, 2),
            monthly_variable_costs_eur=round(variable, 2),
            monthly_contribution_eur=round(contribution, 2),
            monthly_profit_eur=round(profit, 2),
            margin_pct=round(profit / revenue * 100, 1) if revenue > 0 else None,
            break_even_sales_per_month=math.ceil(be_sales) if be_sales is not None else None,
            months_to_recover_setup=round(months, 1) if months is not None else None,
        ))
    return IdeaEconomics(
        idea_id=f.idea_id, price_eur=f.price_eur, pricing_model=f.pricing_model, scenarios=results,
        note="PROGNOSE auf Basis von Annahmen – keine Ist-Zahlen.",
    )


def compute(assessment: FinanceAssessment) -> list[IdeaEconomics]:
    return [compute_idea(i) for i in assessment.ideas]

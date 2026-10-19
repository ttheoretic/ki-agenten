"""Strukturierte Ausgabeformate der Agenten (Pydantic).

Die Modelle sind kompatibel mit dem Strict-JSON-Schema-Modus der OpenAI-API:
keine Defaults, keine freien dicts – optionale Werte sind explizit nullable.
Punktzahlen, Break-even und Summen berechnet ausschließlich das Programm, nicht das Modell.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Confidence = Literal["low", "medium", "high"]
ClaimKind = Literal["fact", "estimate", "hypothesis"]

CRITERIA = (
    "demand", "willingness_to_pay", "automation", "low_cost", "acquisition",
    "feasibility", "scalability", "competitive_advantage", "low_risk",
)
Criterion = Literal[
    "demand", "willingness_to_pay", "automation", "low_cost", "acquisition",
    "feasibility", "scalability", "competitive_advantage", "low_risk",
]


AgentId = Literal["ceo", "research", "strategy", "finance", "product", "builder", "marketing", "sales", "operations", "qa", "analytics"]


class HelpRequest(BaseModel):
    to_agent: AgentId = Field(description="Kollege, der helfen soll (nicht man selbst)")
    question: str = Field(description="Konkrete Frage oder benötigte Zuarbeit")
    reason: str
    blocking: bool = Field(description="true = Ergebnis erst nach der Antwort fertigstellen")


class TeamOutput(BaseModel):
    """Basis aller Agentenausgaben: Jeder Agent kann Kollegen um Hilfe bitten."""

    help_requests: list[HelpRequest] = Field(default_factory=list, description="Hilfeanfragen an Kollegen (max. 2, sonst leer)")


class Consultation(TeamOutput):
    answer: str = Field(description="Konkrete Antwort bzw. Zuarbeit für den Kollegen")
    recommendations: list[str]
    offers: list[str] = Field(description="Weitere Unterstützung, die man anbietet")
    confidence: Confidence


class Source(BaseModel):
    id: str
    title: str
    url: str
    publisher: str
    retrieved_at: str = Field(description="Zeitpunkt der Recherche (ISO-8601)")


class Claim(BaseModel):
    statement: str
    kind: ClaimKind = Field(description="fact nur mit Quelle; estimate = eigene Schätzung; hypothesis = ungeprüfte Annahme")
    source_ids: list[str]
    confidence: Confidence


class Opportunity(BaseModel):
    id: str
    name: str
    model_type: str
    target_group: str
    problem: str
    existing_solutions: list[str]
    price_points: list[str]
    demand_evidence: list[Claim]
    willingness_to_pay_evidence: list[Claim]
    risks: list[str]


class ResearchReport(TeamOutput):
    summary: str
    research_date: str
    opportunities: list[Opportunity]
    information_gaps: list[str]
    sources: list[Source]


class CriterionScore(BaseModel):
    criterion: Criterion
    rating: float = Field(ge=0, le=1, description="0 = sehr schlecht, 1 = sehr gut")
    evidence: str
    confidence: Confidence


class IdeaScore(BaseModel):
    idea_id: str
    name: str
    value_proposition: str
    target_group: str
    monetization: str
    criteria: list[CriterionScore]
    platform_dependencies: list[str]
    kill_criteria: list[str]
    missing_information: list[str]


class Rejection(BaseModel):
    idea_id: str
    reason: str


class Recommendation(BaseModel):
    idea_id: str
    reason: str


class IdeaEvaluation(TeamOutput):
    ideas: list[IdeaScore]
    recommendation: Recommendation
    rejected: list[Rejection]
    selection_criteria: list[str]


class Scenario(BaseModel):
    name: Literal["conservative", "base", "optimistic"]
    monthly_visitors: int = Field(ge=0)
    conversion_rate: float = Field(ge=0, le=1)
    monthly_churn: float = Field(ge=0, le=1)


class IdeaFinance(BaseModel):
    idea_id: str
    pricing_model: Literal["one_time", "subscription", "usage", "service"]
    price_eur: float = Field(ge=0)
    setup_cost_eur: float = Field(ge=0)
    monthly_fixed_costs_eur: float = Field(ge=0)
    variable_cost_per_sale_eur: float = Field(ge=0)
    scenarios: list[Scenario]
    assumptions: list[str]
    budget_risks: list[str]


class FinanceAssessment(TeamOutput):
    ideas: list[IdeaFinance]
    recommendation: str
    unattractive_measures: list[str]
    actuals_vs_forecast: str = Field(description="Abgleich mit tatsächlichen Zahlen; 'keine Ist-Daten', falls keine vorliegen")


class QAIssue(BaseModel):
    severity: Literal["low", "medium", "high", "critical"]
    area: Literal["research", "evidence", "code", "product", "security", "privacy", "legal", "budget", "marketing", "other"]
    description: str
    suggested_fix: str
    suggested_test: str
    target_agent: str


class QAReview(TeamOutput):
    verdict: Literal["pass", "pass_with_issues", "fail"]
    summary: str
    issues: list[QAIssue]
    unsupported_claims: list[str]
    compliance_risks: list[str]
    approvals_required: list[str]


class TaskReview(BaseModel):
    task_id: str
    verdict: Literal["accept", "revise"]
    reason: str


class TaskPriority(BaseModel):
    task_id: str
    priority: int = Field(ge=0, le=100)
    reason: str


class FollowUpRequest(BaseModel):
    agent: Literal["research", "strategy", "finance", "analytics"]
    question: str
    reason: str


class CEOReview(TeamOutput):
    summary: str
    reviews: list[TaskReview]
    priorities: list[TaskPriority]
    follow_ups: list[FollowUpRequest]
    conflicts_detected: list[str]
    next_step: str


class CEODecision(TeamOutput):
    decision: Literal["select", "need_more_info"]
    selected_idea_id: str | None
    rationale: str
    criteria_used: list[str]
    risks_accepted: list[str]
    conditions: list[str]
    open_questions: list[str]


class Feature(BaseModel):
    id: str
    title: str
    priority: Literal["must", "should", "could", "wont"]
    description: str
    acceptance_criteria: list[str]


class UserFlow(BaseModel):
    name: str
    steps: list[str]


class MVPSpec(TeamOutput):
    product_name: str
    problem: str
    target_users: str
    value_proposition: str
    features: list[Feature]
    user_flows: list[UserFlow]
    out_of_scope: list[str]
    validation_plan: list[str]
    success_metrics: list[str]


class BuildFile(BaseModel):
    path: str = Field(description="relativer Pfad innerhalb des Zielordners, z. B. index.html")
    purpose: str
    content: str


class BuildResult(TeamOutput):
    summary: str
    files: list[BuildFile]
    run_instructions: str
    known_limitations: list[str]
    feature_coverage: list[str] = Field(description="Feature-IDs aus der Spezifikation, die umgesetzt wurden")


class ProposedAction(BaseModel):
    action_type: str
    title: str
    description: str
    justification: str
    expected_benefit: str
    cost_eur: float = Field(ge=0)
    recurring_cost_eur: float = Field(ge=0)
    risks: list[str]
    alternatives: list[str]
    params_json: str = Field(description="Parameter der Aktion als JSON-Objekt (Format je Aktionstyp)")


class KeyMessage(BaseModel):
    segment: str
    message: str
    proof_point: str


class PageSection(BaseModel):
    title: str
    body: str


class LandingCopy(BaseModel):
    headline: str
    subheadline: str
    sections: list[PageSection]
    cta: str


class ContentItem(BaseModel):
    week: int
    channel: str
    topic: str
    format: str


class Channel(BaseModel):
    name: str
    rationale: str
    cost_estimate_eur: float
    effort: Literal["low", "medium", "high"]


class Hypothesis(BaseModel):
    id: str
    statement: str
    metric: str
    success_threshold: str


class Positioning(TeamOutput):
    brand_name: str
    tagline: str
    positioning_statement: str
    key_messages: list[KeyMessage]
    landing_page: LandingCopy
    content_plan: list[ContentItem]
    seo_keywords: list[str]
    channels: list[Channel]
    hypotheses: list[Hypothesis]
    external_actions: list[ProposedAction]


class JourneyStep(BaseModel):
    stage: str
    action: str
    metric: str


class LeadSource(BaseModel):
    source: str
    legal_basis: str
    notes: str


class OutreachDraft(BaseModel):
    channel: str
    target_segment: str
    subject: str
    body: str


class Objection(BaseModel):
    objection: str
    response: str


class KPI(BaseModel):
    name: str
    target: str


class SalesPlan(TeamOutput):
    channels: list[Channel]
    customer_journey: list[JourneyStep]
    lead_sources: list[LeadSource]
    outreach_drafts: list[OutreachDraft]
    objections: list[Objection]
    kpis: list[KPI]
    automation_ideas: list[str]
    external_actions: list[ProposedAction]


class RecurringTask(BaseModel):
    name: str
    schedule: str
    owner_agent: str


class OpsPlan(TeamOutput):
    recurring_tasks: list[RecurringTask]
    runbook: list[str]
    monitoring: list[str]
    risks: list[str]
    external_actions: list[ProposedAction]


class Experiment(BaseModel):
    name: str
    hypothesis_id: str
    channel: str
    variant_a: str
    variant_b: str
    metric: str
    duration_days: int
    min_sample_size: int


class ContentDraft(BaseModel):
    channel: str
    title: str
    body: str


class ExperimentPlan(TeamOutput):
    experiments: list[Experiment]
    content_drafts: list[ContentDraft]
    external_actions: list[ProposedAction]


class MetricObservation(BaseModel):
    name: str
    value: float
    source: str


class HypothesisResult(BaseModel):
    hypothesis_id: str
    status: Literal["supported", "rejected", "inconclusive", "no_data"]
    evidence: str


class GrowthRecommendation(BaseModel):
    action: str
    reason: str
    target_agent: str


class AnalyticsReview(TeamOutput):
    data_available: bool
    metrics_used: list[MetricObservation]
    hypothesis_results: list[HypothesisResult]
    recommendations: list[GrowthRecommendation]
    stop_recommendations: list[str]
    experiments_proposed: list[Experiment]
    statistical_notes: str


class FinalDecision(TeamOutput):
    decision: Literal["continue", "pivot", "stop"]
    rationale: str
    lessons: list[str]
    next_steps: list[str]


OUTPUT_SCHEMAS: dict[str, type[BaseModel]] = {
    "market_research": ResearchReport,
    "idea_evaluation": IdeaEvaluation,
    "finance_assessment": FinanceAssessment,
    "qa_review": QAReview,
    "ceo_review": CEOReview,
    "ceo_decision": CEODecision,
    "mvp_spec": MVPSpec,
    "build": BuildResult,
    "positioning": Positioning,
    "sales_plan": SalesPlan,
    "ops_plan": OpsPlan,
    "experiment_plan": ExperimentPlan,
    "analytics_review": AnalyticsReview,
    "final_decision": FinalDecision,
    "consultation": Consultation,
}

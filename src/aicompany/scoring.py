"""Transparente Bewertung von Geschäftsideen (0–100) und Auswahlregeln.

Die Punktzahl ist eine Entscheidungshilfe, kein Erfolgsbeweis. Die Auswahl wird zusätzlich durch
harte Regeln abgesichert (Finance- und QA-Review, fehlende Informationen, kritische Risiken).
"""
from __future__ import annotations

from pydantic import BaseModel

from .agents.schemas import CRITERIA, FinanceAssessment, IdeaEvaluation, IdeaScore, QAReview

WEIGHTS: dict[str, float] = {
    "demand": 20,
    "willingness_to_pay": 15,
    "automation": 15,
    "low_cost": 15,
    "acquisition": 10,
    "feasibility": 10,
    "scalability": 5,
    "competitive_advantage": 5,
    "low_risk": 5,
}
assert sum(WEIGHTS.values()) == 100 and set(WEIGHTS) == set(CRITERIA)

LABELS = {
    "demand": "Nachweisbare Nachfrage",
    "willingness_to_pay": "Zahlungsbereitschaft",
    "automation": "Automatisierbarkeit",
    "low_cost": "Niedrige Start- und Betriebskosten",
    "acquisition": "Einfachheit der Kundengewinnung",
    "feasibility": "Technische Umsetzbarkeit",
    "scalability": "Skalierbarkeit",
    "competitive_advantage": "Wettbewerbsvorteil",
    "low_risk": "Geringes rechtliches/operatives Risiko",
}

CONFIDENCE_FACTOR = {"low": 0.8, "medium": 0.9, "high": 1.0}


class ScoreLine(BaseModel):
    criterion: str
    label: str
    weight: float
    rating: float
    confidence: str
    points: float
    evidence: str


class IdeaScorecard(BaseModel):
    idea_id: str
    name: str
    total: float
    lines: list[ScoreLine]
    missing_information: list[str]
    complete: bool


def score_idea(idea: IdeaScore) -> IdeaScorecard:
    """Punkte = Gewicht × Bewertung × Konfidenzfaktor. Fehlende Kriterien zählen 0 Punkte."""
    by_criterion = {c.criterion: c for c in idea.criteria}
    lines = []
    for crit in CRITERIA:
        c = by_criterion.get(crit)
        if c is None:
            lines.append(ScoreLine(criterion=crit, label=LABELS[crit], weight=WEIGHTS[crit], rating=0, confidence="low",
                                   points=0, evidence="FEHLT – keine Bewertung geliefert"))
            continue
        pts = WEIGHTS[crit] * c.rating * CONFIDENCE_FACTOR[c.confidence]
        lines.append(ScoreLine(criterion=crit, label=LABELS[crit], weight=WEIGHTS[crit], rating=c.rating,
                               confidence=c.confidence, points=round(pts, 2), evidence=c.evidence))
    return IdeaScorecard(
        idea_id=idea.idea_id, name=idea.name, total=round(sum(l.points for l in lines), 1), lines=lines,
        missing_information=idea.missing_information, complete=len(by_criterion) == len(CRITERIA),
    )


def score_all(evaluation: IdeaEvaluation) -> list[IdeaScorecard]:
    return sorted((score_idea(i) for i in evaluation.ideas), key=lambda s: s.total, reverse=True)


class SelectionCheck(BaseModel):
    allowed: bool
    reasons: list[str]
    scorecard: IdeaScorecard | None


def check_selection(
    idea_id: str | None,
    scorecards: list[IdeaScorecard],
    finance: FinanceAssessment | None,
    qa: QAReview | None,
    min_score: float,
) -> SelectionCheck:
    """Harte Auswahlregeln, die das Programm unabhängig von der CEO-Antwort durchsetzt."""
    reasons: list[str] = []
    card = next((s for s in scorecards if s.idea_id == idea_id), None)
    if card is None:
        return SelectionCheck(allowed=False, reasons=[f"Idee '{idea_id}' ist nicht bewertet worden"], scorecard=None)
    if not card.complete:
        reasons.append("Bewertung unvollständig – nicht alle neun Kriterien wurden bewertet")
    if card.total < min_score:
        reasons.append(f"Punktzahl {card.total} liegt unter der Mindestpunktzahl {min_score}")
    if finance is None or not any(f.idea_id == idea_id for f in finance.ideas):
        reasons.append("Kein unabhängiger Finance-Review für diese Idee")
    if qa is None:
        reasons.append("Kein unabhängiger QA-Review")
    else:
        if qa.verdict == "fail":
            reasons.append("QA-Review mit Ergebnis 'fail'")
        critical = [i.description for i in qa.issues if i.severity == "critical"]
        if critical:
            reasons.append("Kritische QA-Befunde offen: " + "; ".join(critical))
    if len(card.missing_information) > 3:
        reasons.append("Zu viele wichtige Informationslücken: " + "; ".join(card.missing_information))
    return SelectionCheck(allowed=not reasons, reasons=reasons, scorecard=card)

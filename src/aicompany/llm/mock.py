"""Dry-Run-Backend: deterministische, eindeutig als SIMULIERT gekennzeichnete Agentenantworten.

Zweck: den vollständigen Ablauf (Orchestrierung, Budget, Freigaben, Überarbeitungen, UI) ohne
API-Kosten testen. Die Inhalte sind Platzhalter – sie sind KEINE Marktrecherche. Alle Quellen
zeigen auf `example.invalid` und tragen den Hinweis „SIMULIERT“.

Fehlerinjektion für Tests: `fail_plan` (vorübergehende API-Fehler), `invalid_plan` (Schemafehler)
und `semantic_invalid_plan` (formal gültig, aber inhaltlich unzulässig) je Aufgaben-Key.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from ..agents.schemas import (
    AnalyticsReview, BuildFile, Consultation, HelpRequest, BuildResult, CEODecision, CEOReview, Channel, Claim, ContentDraft, ContentItem,
    CriterionScore, Experiment, ExperimentPlan, Feature, FinalDecision, FinanceAssessment, GrowthRecommendation,
    Hypothesis, HypothesisResult, IdeaEvaluation, IdeaFinance, IdeaScore, JourneyStep, KeyMessage, KPI, LandingCopy,
    LeadSource, MetricObservation, MVPSpec, Objection, OpsPlan, Opportunity, OutreachDraft, PageSection, Positioning,
    ProposedAction, QAIssue, QAReview, Recommendation, RecurringTask, Rejection, ResearchReport, SalesPlan, Scenario,
    Source, TaskPriority, TaskReview, UserFlow,
)
from ..budget import CallUsage
from .base import AgentCall, AgentCallResult, LLMOutputError, LLMTransientError

SIM = "[SIMULIERT] "
DATE = "2026-01-01T00:00:00Z"

OPPS = [
    ("angebotsrechner-handwerk", "Angebots- & Stundensatzrechner mit Vorlagenpaket für Handwerksbetriebe", "Digitales Produkt / Mini-SaaS",
     "Kleine Handwerksbetriebe (1–10 Mitarbeitende)", "Angebote werden zeitaufwendig in Word/Excel erstellt, Stundensätze oft falsch kalkuliert"),
    ("preisreport-onlineshops", "Wöchentlicher Wettbewerbspreis-Report für kleine Onlineshops", "Recherche- und Berichtsdienst",
     "Inhabergeführte Onlineshops", "Preisbeobachtung der Konkurrenz kostet Zeit"),
    ("protokoll-automation", "KI-Workflow für Sitzungsprotokolle in Vereinen", "Automatisierungswerkzeug",
     "Vereinsvorstände", "Protokolle sind lästig und werden verspätet verschickt"),
    ("foerdercheck-kmu", "Fördermittel-Vorabcheck für Kleinunternehmen", "Spezialisierte Webanwendung",
     "Gründerinnen und Gründer", "Förderlandschaft ist unübersichtlich"),
    ("dsgvo-vorlagen-vereine", "DSGVO-Vorlagenpaket für Vereine", "Digitale Vorlagen",
     "Kleine Vereine", "Unsicherheit bei Datenschutzpflichten"),
]

RATINGS = {
    "angebotsrechner-handwerk": dict(demand=0.7, willingness_to_pay=0.65, automation=0.85, low_cost=0.9, acquisition=0.55,
                                     feasibility=0.9, scalability=0.8, competitive_advantage=0.5, low_risk=0.8),
    "preisreport-onlineshops": dict(demand=0.6, willingness_to_pay=0.6, automation=0.7, low_cost=0.7, acquisition=0.5,
                                    feasibility=0.6, scalability=0.7, competitive_advantage=0.4, low_risk=0.5),
    "protokoll-automation": dict(demand=0.5, willingness_to_pay=0.35, automation=0.8, low_cost=0.6, acquisition=0.45,
                                 feasibility=0.7, scalability=0.7, competitive_advantage=0.3, low_risk=0.3),
    "foerdercheck-kmu": dict(demand=0.6, willingness_to_pay=0.4, automation=0.5, low_cost=0.7, acquisition=0.4,
                             feasibility=0.5, scalability=0.6, competitive_advantage=0.4, low_risk=0.2),
    "dsgvo-vorlagen-vereine": dict(demand=0.55, willingness_to_pay=0.45, automation=0.9, low_cost=0.9, acquisition=0.5,
                                   feasibility=0.9, scalability=0.8, competitive_advantage=0.2, low_risk=0.25),
}


def _dep(call: AgentCall, kind: str) -> dict | None:
    items = call.context.get("deps_by_kind", {}).get(kind) or []
    return items[-1] if items else None


def _action(action_type: str, title: str, params: dict, cost: float = 0.0, recurring: float = 0.0, **kw: Any) -> ProposedAction:
    return ProposedAction(
        action_type=action_type, title=title, description=kw.get("description", SIM + title),
        justification=kw.get("justification", SIM + "Voraussetzung für den Markttest"),
        expected_benefit=kw.get("benefit", SIM + "Erste messbare Marktreaktion"), cost_eur=cost, recurring_cost_eur=recurring,
        risks=kw.get("risks", ["Simulierter Antrag – vor Genehmigung Inhalte prüfen"]),
        alternatives=kw.get("alternatives", ["Aktion verschieben"]), params_json=json.dumps(params, ensure_ascii=False),
    )


def _totals(metrics: list[dict]) -> dict[str, float]:
    out: dict[str, float] = {}
    for m in metrics:
        out[m["name"]] = out.get(m["name"], 0.0) + float(m["value"])
    return out


class MockBackend:
    name = "dry-run-mock"
    simulated = True

    def __init__(self, *, fail_plan: dict[str, int] | None = None, invalid_plan: dict[str, int] | None = None,
                 semantic_invalid_plan: dict[str, int] | None = None, delay_seconds: float = 0.0):
        self.fail_plan = dict(fail_plan or {})
        self.invalid_plan = dict(invalid_plan or {})
        self.semantic_invalid_plan = dict(semantic_invalid_plan or {})
        self.delay = delay_seconds
        self.calls: list[str] = []

    async def run(self, call: AgentCall) -> AgentCallResult:
        self.calls.append(call.task_key)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail_plan.get(call.task_key, 0) > 0:
            self.fail_plan[call.task_key] -= 1
            raise LLMTransientError("Simulierter API-Ausfall (503)")
        if self.invalid_plan.get(call.task_key, 0) > 0:
            self.invalid_plan[call.task_key] -= 1
            raise LLMOutputError("Simulierte ungültige Ausgabe: JSON entspricht nicht dem Schema")
        gen = getattr(self, f"_gen_{call.kind}")
        output = gen(call)
        if call.kind != "consultation" and not call.context.get("team_notes"):
            output.help_requests = self._help_requests(call)
        if self.semantic_invalid_plan.get(call.task_key, 0) > 0:
            self.semantic_invalid_plan[call.task_key] -= 1
            output = self._break(output)
        text = output.model_dump_json()
        usage = CallUsage(input_tokens=len(call.prompt) // 4 + len(call.instructions) // 4,
                          output_tokens=min(len(text) // 4, call.max_output_tokens), requests=1,
                          web_search_calls=2 if "web_search" in call.tools else 0)
        return AgentCallResult(output=output, usage=usage, model=call.model, simulated=True,
                               cited_urls=[f"https://example.invalid/dry-run/{i}" for i in range(1, 6)],
                               web_search_calls=usage.web_search_calls)

    @staticmethod
    def _break(output):
        if isinstance(output, ResearchReport):
            output.opportunities[0].demand_evidence[0].source_ids = []  # Fakt ohne Quelle
            output.opportunities[0].demand_evidence[0].kind = "fact"
        elif isinstance(output, AnalyticsReview):
            output.metrics_used.append(MetricObservation(name="revenue_eur", value=999.0, source="erfunden"))
        elif isinstance(output, BuildResult):
            output.files.append(BuildFile(path="../escape.sh", purpose="unzulässig", content="rm -rf /"))
        return output

    # ---------- Teamarbeit (simuliert, deterministisch) ----------
    @staticmethod
    def _help_requests(call: AgentCall) -> list[HelpRequest]:
        """Typische Rückfragen unter Kollegen – nur beim ersten Versuch, solange noch keine Antwort vorliegt."""
        if call.revision:
            return []
        if call.kind == "positioning":
            return [HelpRequest(to_agent="finance", question="Welcher Preisrahmen ist realistisch, damit ich ihn auf der Landingpage nennen kann?",
                                reason=SIM + "Preisaussage auf der Landingpage muss wirtschaftlich tragfähig sein", blocking=True)]
        if call.kind == "mvp_spec" and call.context.get("cycle_type") != "operate":
            return [HelpRequest(to_agent="marketing", question="Welche Funktion überzeugt die Zielgruppe am meisten?",
                                reason=SIM + "Must-Features nach Kundennutzen priorisieren", blocking=False)]
        if call.kind == "sales_plan":
            return [HelpRequest(to_agent="qa", question="Ist die geplante Kontaktaufnahme rechtlich sauber (DSGVO/UWG)?",
                                reason=SIM + "Keine Kaltakquise ohne Rechtsgrundlage", blocking=True)]
        if call.kind == "analytics_review" and call.context.get("cycle_type") == "operate":
            return [HelpRequest(to_agent="sales", question="Welche Rückmeldungen und Einwände kamen von Interessenten?",
                                reason=SIM + "Zahlen mit qualitativem Feedback ergänzen", blocking=False)]
        return []

    def _gen_consultation(self, call: AgentCall) -> Consultation:
        inp = call.context.get("task_inputs", {})
        who = inp.get("requester", "Kollege")
        if inp.get("mode") == "offer":
            return Consultation(answer=SIM + f"Ich habe mir die Rückmeldung angesehen und schlage vor, zuerst den kritischsten Punkt zu beheben "
                                f"und ihn mit einem kleinen Test abzusichern. Aus meiner Sicht als {call.agent_id} ist das umsetzbar.",
                                recommendations=["Kritischsten Befund zuerst beheben", "Akzeptanzkriterium als Test formulieren"],
                                offers=[f"Ich prüfe die überarbeitete Version für {who} gern vorab"], confidence="medium")
        answers = {
            "finance": "Ein Einmalpreis von 19–29 € deckt Gebühren und Hosting bereits ab 3 Verkäufen im Monat.",
            "marketing": "Der Stundensatzrechner ist der stärkste Aufhänger – er löst das Problem sofort sichtbar.",
            "qa": "Kontakt nur nach eigener Anfrage oder mit dokumentierter Einwilligung; keine gekauften Listen, Impressum verlinken.",
            "sales": "Bisher gab es eine Anfrage; der häufigste Einwand ist der Wechselaufwand weg von Excel.",
        }
        return Consultation(answer=SIM + answers.get(call.agent_id, "Hier ist meine Einschätzung aus meiner Fachrolle."),
                            recommendations=[SIM + "Empfehlung in das Ergebnis übernehmen"],
                            offers=[f"Bei Rückfragen helfe ich {who} gern weiter"], confidence="medium")

    # ---------- Generatoren je Aufgabenart ----------
    def _gen_market_research(self, call: AgentCall) -> ResearchReport:
        sources = [Source(id=f"S{i}", title=f"SIMULIERTE QUELLE {i} (Dry-Run, keine echte Recherche)",
                          url=f"https://example.invalid/dry-run/{i}", publisher="Dry-Run", retrieved_at=DATE) for i in range(1, 6)]
        opps = []
        for n, (oid, name, mtype, group, problem) in enumerate(OPPS):
            opps.append(Opportunity(
                id=oid, name=name, model_type=mtype, target_group=group, problem=problem,
                existing_solutions=[SIM + "Allgemeine Tabellenvorlagen", SIM + "Branchen-Software mit hohem Preis"],
                price_points=[SIM + "19–49 € einmalig", SIM + "9–19 € pro Monat"],
                demand_evidence=[
                    Claim(statement=SIM + f"Diskussionen zu „{problem}“ in Fachforen", kind="fact", source_ids=[f"S{n % 5 + 1}"], confidence="medium"),
                    Claim(statement=SIM + "Zielgruppe ist groß genug für eine Nische", kind="estimate", source_ids=[], confidence="low"),
                ],
                willingness_to_pay_evidence=[Claim(statement=SIM + "Vergleichbare Produkte werden verkauft", kind="hypothesis", source_ids=[], confidence="low")],
                risks=[SIM + "Nachfrage ist nur indirekt belegt"],
            ))
        return ResearchReport(
            summary=SIM + "Fünf Nischen untersucht; Belege sind Platzhalter des Dry-Runs.", research_date=DATE,
            opportunities=opps, information_gaps=[SIM + "Echte Zahlungsbereitschaft nur über Markttest prüfbar",
                                                  SIM + "Marktgröße nicht belastbar bestimmt"], sources=sources,
        )

    def _gen_idea_evaluation(self, call: AgentCall) -> IdeaEvaluation:
        research = _dep(call, "market_research") or {}
        ids = [o["id"] for o in research.get("opportunities", [])] or list(RATINGS)
        names = {o["id"]: o["name"] for o in research.get("opportunities", [])}
        ideas = []
        for oid in ids:
            r = RATINGS.get(oid, {c: 0.5 for c in RATINGS["angebotsrechner-handwerk"]})
            ideas.append(IdeaScore(
                idea_id=oid, name=names.get(oid, oid), value_proposition=SIM + "Spart Zeit bei einer wiederkehrenden Aufgabe",
                target_group=SIM + "siehe Recherche", monetization=SIM + "Einmalkauf oder kleines Abo",
                criteria=[CriterionScore(criterion=c, rating=v, evidence=SIM + f"Begründung für {c}", confidence="medium") for c, v in r.items()],
                platform_dependencies=[SIM + "Zahlungsanbieter", SIM + "Hosting"],
                kill_criteria=[SIM + "Weniger als 1 % Conversion nach 300 Besuchern"],
                missing_information=[SIM + "Echte Zahlungsbereitschaft"],
            ))
        excluded = set(call.context.get("excluded_ideas") or [])
        ranked = sorted((i for i in ideas if i.idea_id not in excluded),
                        key=lambda i: -sum(c.rating for c in i.criteria))
        best = ranked[0].idea_id if ranked else ideas[0].idea_id
        return IdeaEvaluation(
            ideas=ideas, recommendation=Recommendation(idea_id=best, reason=SIM + "Beste noch nicht versuchte Kombination aus Umsetzbarkeit, Kosten und Risiko"),
            rejected=[Rejection(idea_id="foerdercheck-kmu", reason=SIM + "Rechtliches Risiko durch Beratungsnähe"),
                      Rejection(idea_id="protokoll-automation", reason=SIM + "Datenschutzrisiko (personenbezogene Inhalte)")],
            selection_criteria=[SIM + "Punktzahl ≥ Mindestwert", SIM + "kein kritisches Risiko", SIM + "MVP in < 1 Woche baubar"],
        )

    def _gen_finance_assessment(self, call: AgentCall) -> FinanceAssessment:
        evaluation = _dep(call, "idea_evaluation") or {}
        ids = [i["idea_id"] for i in evaluation.get("ideas", [])][:3] or ["angebotsrechner-handwerk"]
        if call.context.get("selected_idea"):
            ids = [call.context["selected_idea"]["id"]]
        elif evaluation.get("recommendation", {}).get("idea_id") and evaluation["recommendation"]["idea_id"] not in ids:
            ids = [evaluation["recommendation"]["idea_id"]] + ids[:2]
        ideas = [IdeaFinance(
            idea_id=i, pricing_model="one_time", price_eur=29.0, setup_cost_eur=0.0, monthly_fixed_costs_eur=8.0,
            variable_cost_per_sale_eur=1.6,
            scenarios=[Scenario(name="conservative", monthly_visitors=150, conversion_rate=0.005, monthly_churn=0),
                       Scenario(name="base", monthly_visitors=400, conversion_rate=0.01, monthly_churn=0),
                       Scenario(name="optimistic", monthly_visitors=1000, conversion_rate=0.02, monthly_churn=0)],
            assumptions=[SIM + "Hosting ~5 €/Monat, Domain ~3 €/Monat", SIM + "Zahlungsgebühr ~5,5 % je Verkauf"],
            budget_risks=[SIM + "Bezahlte Werbung würde das Budget schnell aufbrauchen"],
        ) for i in ids]
        has_actuals = bool(call.context.get("metrics"))
        return FinanceAssessment(
            ideas=ideas, recommendation=SIM + "Einmalpreis 29 €; ohne Werbebudget starten",
            unattractive_measures=[SIM + "Bezahlte Anzeigen vor Nachweis der Conversion"],
            actuals_vs_forecast="Ist-Daten liegen vor und wurden berücksichtigt" if has_actuals else "keine Ist-Daten",
        )

    def _gen_qa_review(self, call: AgentCall) -> QAReview:
        target = call.context.get("review_target") or {}
        checks = call.context.get("automated_checks") or {}
        failed_checks = [c for c in checks.get("checks", []) if not c["passed"]]
        if failed_checks:
            return QAReview(verdict="fail", summary=SIM + "Automatische Prüfungen fehlgeschlagen",
                            issues=[QAIssue(severity="high", area="code", description=c["name"] + ": " + c["detail"],
                                            suggested_fix=SIM + "Prüfung beheben", suggested_test=SIM + "Prüfung erneut ausführen",
                                            target_agent=target.get("agent", "builder")) for c in failed_checks],
                            unsupported_claims=[], compliance_risks=[], approvals_required=[])
        if target.get("kind") == "build" and target.get("revision_count", 0) == 0 and "product" in str(target.get("key", "")):
            # Simuliertes realistisches Ergebnis: erster Build hat einen Mangel → Rückgabe an Builder
            return QAReview(
                verdict="fail", summary=SIM + "Funktionsprüfung: Eingabevalidierung fehlt",
                issues=[QAIssue(severity="high", area="code", description=SIM + "Negative Stundenzahlen werden akzeptiert",
                                suggested_fix=SIM + "Eingaben auf ≥ 0 begrenzen und Fehlermeldung anzeigen",
                                suggested_test=SIM + "Eingabe -5 Stunden → Fehlermeldung erwartet", target_agent="builder")],
                unsupported_claims=[], compliance_risks=[], approvals_required=[],
            )
        compliance = "compliance" in call.task_key
        return QAReview(
            verdict="pass_with_issues" if compliance else "pass",
            summary=SIM + ("Compliance-Prüfung bestanden mit Auflagen" if compliance else "Prüfung bestanden"),
            issues=[QAIssue(severity="medium", area="legal", description=SIM + "Impressum und Datenschutzerklärung enthalten Platzhalter",
                            suggested_fix="Vor Veröffentlichung durch den Eigentümer ausfüllen lassen",
                            suggested_test="Seite auf '[Vom Eigentümer auszufüllen]' durchsuchen", target_agent="operations")] if compliance else [],
            unsupported_claims=[SIM + "Nachfragebelege sind simuliert"] if "selection" in call.task_key else [],
            compliance_risks=[SIM + "Impressumspflicht (DDG) beachten"] if compliance else [],
            approvals_required=["publish_website"] if compliance else [],
        )

    def _gen_ceo_review(self, call: AgentCall) -> CEOReview:
        reviews = []
        for t in call.context.get("review_tasks", []):
            if t["kind"] == "positioning" and t["revision_count"] == 0:
                reviews.append(TaskReview(task_id=t["id"], verdict="revise", reason=SIM + "Wertversprechen schärfen: konkrete Zeitersparnis statt allgemeiner Aussagen"))
            else:
                reviews.append(TaskReview(task_id=t["id"], verdict="accept", reason=SIM + "Akzeptanzkriterien erfüllt"))
        prios = [TaskPriority(task_id=t["id"], priority=min(100, t["priority"] + 5), reason=SIM + "kritischer Pfad")
                 for t in call.context.get("ready_tasks", [])[:2]]
        return CEOReview(summary=SIM + "Lage geprüft, nächste Aufgaben priorisiert", reviews=reviews, priorities=prios,
                         follow_ups=[], conflicts_detected=[], next_step=SIM + "Kritischen Pfad fortsetzen")

    def _gen_ceo_decision(self, call: AgentCall) -> CEODecision:
        cards = call.context.get("scorecards", [])
        best = cards[0]["idea_id"] if cards else "angebotsrechner-handwerk"
        return CEODecision(decision="select", selected_idea_id=best, rationale=SIM + "Höchste Punktzahl, Finance und QA ohne kritische Befunde",
                           criteria_used=["Punktzahl", "Finance-Review", "QA-Review", "Risiko"],
                           risks_accepted=[SIM + "Nachfrage nur indirekt belegt – Markttest notwendig"],
                           conditions=[SIM + "Kein Werbebudget vor 300 organischen Besuchern"], open_questions=[])

    def _gen_mvp_spec(self, call: AgentCall) -> MVPSpec:
        idea = call.context.get("selected_idea") or {"name": "Produkt"}
        return MVPSpec(
            product_name="Angebotsrechner Handwerk", problem=SIM + idea.get("name", ""), target_users=SIM + "Inhaber kleiner Handwerksbetriebe",
            value_proposition=SIM + "In 2 Minuten ein kalkuliertes Angebot statt 30 Minuten in Excel",
            features=[
                Feature(id="F1", title="Stundensatzrechner", priority="must", description="Kosten → kostendeckender Stundensatz",
                        acceptance_criteria=["Ergebnis wird bei gültigen Eingaben angezeigt", "Negative Werte werden abgewiesen"]),
                Feature(id="F2", title="Angebotsposten", priority="must", description="Material + Arbeitszeit → Angebotssumme",
                        acceptance_criteria=["Summe inkl. MwSt. wird berechnet"]),
                Feature(id="F3", title="Vorlagenpaket", priority="should", description="Angebots-/Rechnungsvorlagen als Text",
                        acceptance_criteria=["Mindestens eine Vorlage im Paket"]),
                Feature(id="F4", title="Kundenkonten", priority="wont", description="Nicht im MVP", acceptance_criteria=[]),
            ],
            user_flows=[UserFlow(name="Angebot kalkulieren", steps=["Kosten eingeben", "Stundensatz erhalten", "Posten erfassen", "Summe kopieren"])],
            out_of_scope=["Benutzerkonten", "Speicherung personenbezogener Daten", "Zahlungsabwicklung im Tool"],
            validation_plan=[SIM + "Landingpage mit Preis testen, bevor weitere Funktionen gebaut werden"],
            success_metrics=["Besucher→Kauf-Conversion ≥ 1 %", "≥ 3 qualifizierte Anfragen in 10 Tagen"],
        )

    def _gen_build(self, call: AgentCall) -> BuildResult:
        target = call.context.get("target_dir", "product")
        fixed = call.revision > 0
        if target == "site":
            pos = _dep(call, "positioning") or {}
            lp = pos.get("landing_page", {})
            sections = "".join(f"<section><h2>{s['title']}</h2><p>{s['body']}</p></section>" for s in lp.get("sections", []))
            html = (f"<!doctype html><html lang=\"de\"><head><meta charset=\"utf-8\"><title>{pos.get('brand_name', 'Produkt')}</title>"
                    f"<link rel=\"stylesheet\" href=\"styles.css\"></head><body><header><h1>{lp.get('headline', '')}</h1>"
                    f"<p>{lp.get('subheadline', '')}</p></header>{sections}<p class=\"price\">Preis: 29 € einmalig (inkl. MwSt.)</p>"
                    f"<a class=\"cta\" href=\"mailto:kontakt@example.invalid\">{lp.get('cta', 'Anfragen')}</a>"
                    "<footer><a href=\"impressum.html\">Impressum</a> · <a href=\"datenschutz.html\">Datenschutz</a></footer></body></html>")
            files = [
                BuildFile(path="index.html", purpose="Landingpage", content=html),
                BuildFile(path="styles.css", purpose="Gestaltung", content="body{font-family:system-ui;max-width:760px;margin:auto;padding:24px}.cta{display:inline-block;padding:12px 20px;background:#2563eb;color:#fff;border-radius:8px}"),
                BuildFile(path="impressum.html", purpose="Impressum (Platzhalter)", content="<!doctype html><html lang=\"de\"><head><meta charset=\"utf-8\"><title>Impressum</title></head><body><h1>Impressum</h1><p>[Vom Eigentümer auszufüllen]</p></body></html>"),
                BuildFile(path="datenschutz.html", purpose="Datenschutzerklärung (Platzhalter)", content="<!doctype html><html lang=\"de\"><head><meta charset=\"utf-8\"><title>Datenschutz</title></head><body><h1>Datenschutzerklärung</h1><p>Diese Seite setzt keine Cookies und kein Tracking ein.</p><p>[Vom Eigentümer auszufüllen]</p></body></html>"),
            ]
            return BuildResult(summary=SIM + "Statische Landingpage ohne Tracking erstellt", files=files,
                               run_instructions="index.html im Browser öffnen", known_limitations=["Impressum ist Platzhalter"],
                               feature_coverage=["LP"])
        validation = ("if(h<0||k<0||m<0){out.textContent='Bitte nur Werte ≥ 0 eingeben.';return;}" if fixed else "")
        js = ("function calc(){const k=+document.getElementById('kosten').value,h=+document.getElementById('stunden').value,"
              "m=+document.getElementById('material').value;const out=document.getElementById('out');" + validation +
              "if(!h){out.textContent='Bitte produktive Stunden angeben.';return;}const satz=k/h;const netto=satz*8+m;"
              "out.textContent='Stundensatz: '+satz.toFixed(2)+' € | Angebot (8 h + Material) inkl. 19 % MwSt.: '+(netto*1.19).toFixed(2)+' €';}"
              "document.getElementById('calc').addEventListener('click',calc);")
        html = ("<!doctype html><html lang=\"de\"><head><meta charset=\"utf-8\"><title>Angebotsrechner Handwerk</title>"
                "<link rel=\"stylesheet\" href=\"styles.css\"></head><body><h1>Angebotsrechner</h1>"
                "<label>Monatliche Kosten (€) <input id=\"kosten\" type=\"number\" min=\"0\" value=\"6000\"></label>"
                "<label>Produktive Stunden/Monat <input id=\"stunden\" type=\"number\" min=\"0\" value=\"120\"></label>"
                "<label>Material (€) <input id=\"material\" type=\"number\" min=\"0\" value=\"150\"></label>"
                "<button id=\"calc\">Berechnen</button><p id=\"out\"></p><script src=\"app.js\"></script></body></html>")
        files = [
            BuildFile(path="index.html", purpose="Rechner-Oberfläche", content=html),
            BuildFile(path="app.js", purpose="Berechnungslogik", content=js),
            BuildFile(path="styles.css", purpose="Gestaltung", content="body{font-family:system-ui;max-width:640px;margin:auto;padding:24px}label{display:block;margin:8px 0}"),
            BuildFile(path="vorlagen/angebot.md", purpose="Angebotsvorlage", content="# Angebot\n\nPosition | Menge | Preis\n---|---|---\n"),
            BuildFile(path="README.md", purpose="Dokumentation", content="# Angebotsrechner\n\nStatische Anwendung ohne Datenspeicherung. `index.html` öffnen.\n"),
        ]
        return BuildResult(summary=SIM + ("Version 2: Eingabevalidierung ergänzt" if fixed else "Version 1 des Rechners"), files=files,
                           run_instructions="index.html im Browser öffnen", known_limitations=["Keine Speicherung", "Keine PDF-Ausgabe"],
                           feature_coverage=["F1", "F2", "F3"])

    def _gen_positioning(self, call: AgentCall) -> Positioning:
        sharpened = call.revision > 0
        headline = "Angebote in 2 Minuten statt 30 – mit korrektem Stundensatz" if sharpened else "Der Angebotsrechner fürs Handwerk"
        return Positioning(
            brand_name="Angebotsrechner Handwerk", tagline="Richtig kalkulieren, schneller anbieten",
            positioning_statement=SIM + "Für kleine Handwerksbetriebe, die Angebote schneller und kostendeckend erstellen wollen",
            key_messages=[KeyMessage(segment="Inhaber", message="Kostendeckender Stundensatz auf Knopfdruck", proof_point="Rechenweg ist offen einsehbar")],
            landing_page=LandingCopy(headline=headline, subheadline="Kein Abo, keine Datenspeicherung, sofort nutzbar",
                                     sections=[PageSection(title="So funktioniert es", body="Kosten eingeben, Stundensatz erhalten, Angebot kalkulieren."),
                                               PageSection(title="Was enthalten ist", body="Rechner und Vorlagenpaket für Angebote und Rechnungen.")],
                                     cta="Jetzt Interesse melden"),
            content_plan=[ContentItem(week=1, channel="Blog", topic="Stundensatz richtig berechnen", format="Artikel"),
                          ContentItem(week=2, channel="LinkedIn", topic="3 Fehler bei Angeboten", format="Beitrag")],
            seo_keywords=["stundensatz handwerker berechnen", "angebot vorlage handwerk"],
            channels=[Channel(name="SEO-Artikel", rationale="Suchintention passt", cost_estimate_eur=0, effort="medium"),
                      Channel(name="Fachgruppen (mit Erlaubnis der Admins)", rationale="Direkter Zielgruppenzugang", cost_estimate_eur=0, effort="medium")],
            hypotheses=[Hypothesis(id="H1", statement="≥ 1 % der Besucher melden Kaufinteresse", metric="conversion_rate", success_threshold="0.01"),
                        Hypothesis(id="H2", statement="SEO-Artikel bringen ≥ 100 Besucher in 10 Tagen", metric="visitors", success_threshold="100")],
            external_actions=[],
        )

    def _gen_sales_plan(self, call: AgentCall) -> SalesPlan:
        return SalesPlan(
            channels=[Channel(name="Landingpage + Interessentenformular per E-Mail-Link", rationale="geringe Kosten", cost_estimate_eur=0, effort="low")],
            customer_journey=[JourneyStep(stage="Aufmerksamkeit", action="Artikel lesen", metric="visitors"),
                              JourneyStep(stage="Interesse", action="Rechner testen", metric="tool_uses"),
                              JourneyStep(stage="Kauf", action="Vorlagenpaket kaufen", metric="sales")],
            lead_sources=[LeadSource(source="Eigene Website-Anfragen", legal_basis="Anfrage durch die Person selbst (Art. 6 Abs. 1 lit. b DSGVO)", notes="kein Kaltakquise-Versand")],
            outreach_drafts=[OutreachDraft(channel="E-Mail (nur auf Anfrage)", target_segment="Interessenten", subject="Ihr Angebotsrechner",
                                           body=SIM + "Danke für Ihr Interesse – hier ist der Link zum Rechner.")],
            objections=[Objection(objection="Ich nutze schon Excel", response="Der Rechner ersetzt Excel nicht, er prüft den Stundensatz in 2 Minuten.")],
            kpis=[KPI(name="Anfragen", target="≥ 3 in 10 Tagen"), KPI(name="Verkäufe", target="≥ 1 im Testzeitraum")],
            automation_ideas=[SIM + "Automatische Antwort-Vorlage bei Anfragen (Versand nur nach Freigabe)"],
            external_actions=[],
        )

    def _gen_ops_plan(self, call: AgentCall) -> OpsPlan:
        if call.context.get("cycle_type") == "operate":
            return OpsPlan(
                recurring_tasks=[RecurringTask(name="Kennzahlen-Review", schedule="wöchentlich", owner_agent="analytics")],
                runbook=["Neue Version erst nach QA-Freigabe und Eigentümer-Freigabe veröffentlichen"],
                monitoring=["Budget", "Fehler", "offene Freigaben"], risks=[],
                external_actions=[_action("publish_website", f"Produktversion aus Zyklus {call.context.get('cycle')} veröffentlichen (lokales Release-Paket)",
                                          {"source_dir": "product", "target": "local_release"},
                                          justification=SIM + "QA-geprüfte Verbesserungen ausliefern")],
            )
        return OpsPlan(
            recurring_tasks=[RecurringTask(name="Kennzahlen-Review", schedule="alle 3 Tage", owner_agent="analytics"),
                             RecurringTask(name="Managementbericht", schedule="nach jedem Lauf", owner_agent="ceo")],
            runbook=["Bei API-Fehlern: Lauf endet, Aufgaben bleiben 'pending' und werden beim nächsten Lauf fortgesetzt",
                     "Bei Budgetwarnung 90 %: nur noch kritische Aufgaben"],
            monitoring=["Budgetverbrauch", "fehlgeschlagene Aufgaben", "offene Freigaben"],
            risks=[SIM + "Impressum muss vor Veröffentlichung ausgefüllt sein"],
            external_actions=[_action("publish_website", "Landingpage veröffentlichen (lokales Release-Paket)",
                                      {"source_dir": "site", "target": "local_release"},
                                      justification=SIM + "Ohne erreichbare Seite kein Markttest",
                                      risks=["Impressum/Datenschutz müssen vorher ausgefüllt sein"],
                                      alternatives=["Nur Vorschau intern teilen"])],
        )

    def _gen_experiment_plan(self, call: AgentCall) -> ExperimentPlan:
        return ExperimentPlan(
            experiments=[Experiment(name="Headline-Test", hypothesis_id="H1", channel="Landingpage", variant_a="Zeitersparnis",
                                    variant_b="Kostendeckung", metric="conversion_rate", duration_days=7, min_sample_size=300)],
            content_drafts=[ContentDraft(channel="LinkedIn", title="Stundensatz richtig berechnen", body=SIM + "Entwurf eines Fachbeitrags ohne Werbeversprechen.")],
            external_actions=[
                _action("publish_content", "Fachbeitrag auf LinkedIn veröffentlichen", {"platform": "linkedin", "content_path": "marketing/beitrag-1.md"}),
                _action("paid_ads", "Kleiner Anzeigentest (15 €)", {"vendor": "Suchmaschinenwerbung", "description": "Test 7 Tage", "amount_eur": 15.0, "recurring": "none"},
                        cost=15.0, justification=SIM + "Schnellere Datenbasis für H1", risks=["Budgetverbrauch ohne Conversion"],
                        alternatives=["Nur organische Kanäle nutzen (0 €)"]),
            ],
        )

    def _gen_analytics_review(self, call: AgentCall) -> AnalyticsReview:
        metrics = call.context.get("metrics", [])
        if not metrics:
            return AnalyticsReview(
                data_available=False, metrics_used=[],
                hypothesis_results=[HypothesisResult(hypothesis_id="H1", status="no_data", evidence="Keine Messwerte vorhanden"),
                                    HypothesisResult(hypothesis_id="H2", status="no_data", evidence="Keine Messwerte vorhanden")],
                recommendations=[GrowthRecommendation(action="Messung starten: Besucher, Anfragen und Verkäufe im Control-Center erfassen",
                                                      reason="Ohne Daten keine Bewertung möglich", target_agent="ceo")],
                stop_recommendations=[], experiments_proposed=[],
                statistical_notes="Keine Daten – keine Aussage möglich.",
            )
        used = [MetricObservation(name=m["name"], value=m["value"], source=m["source"]) for m in metrics]
        totals = _totals(metrics)
        if totals.get("visitors", 0) >= 300 and totals.get("sales", 0) == 0:
            return AnalyticsReview(
                data_available=True, metrics_used=used,
                hypothesis_results=[HypothesisResult(hypothesis_id="H1", status="rejected",
                                                     evidence=f"{totals['visitors']:.0f} Besucher, 0 Verkäufe – Mindeststichprobe erreicht")],
                recommendations=[GrowthRecommendation(action="Kurswechsel prüfen: Angebot findet trotz Reichweite keine Käufer",
                                                      reason="H1 widerlegt", target_agent="ceo")],
                stop_recommendations=["Aktuelle Ansprache nicht weiter skalieren"], experiments_proposed=[],
                statistical_notes="Mindeststichprobe erreicht; Ergebnis ist ein Signal, kein Kausalbeweis.",
            )
        return AnalyticsReview(
            data_available=True, metrics_used=used,
            hypothesis_results=[HypothesisResult(hypothesis_id="H1", status="inconclusive", evidence="Stichprobe unter Mindestgröße")],
            recommendations=[GrowthRecommendation(action="Test fortsetzen, bis Mindeststichprobe erreicht ist", reason="geringe Aussagekraft", target_agent="marketing")],
            stop_recommendations=[], experiments_proposed=[], statistical_notes="Kleine Stichprobe; keine kausalen Schlüsse.",
        )

    def _gen_final_decision(self, call: AgentCall) -> FinalDecision:
        totals = _totals(call.context.get("metrics", []))
        if totals.get("visitors", 0) >= 300 and totals.get("sales", 0) == 0:
            return FinalDecision(decision="pivot", rationale=SIM + f"{totals['visitors']:.0f} Besucher, aber 0 Verkäufe – die Nische trägt nicht. "
                                 "Kurswechsel zur nächstbesten noch nicht versuchten Idee.",
                                 lessons=["Reichweite allein reicht nicht – Zahlungsbereitschaft früher testen"],
                                 next_steps=["Nächstbeste Idee neu bewerten", "Vorhandene Landingpage-Bausteine wiederverwenden"])
        if totals.get("sales", 0) > 0:
            return FinalDecision(decision="continue", rationale=SIM + f"{totals['sales']:.0f} Verkäufe – Nachfrage belegt, Betrieb fortsetzen",
                                 lessons=["Kanal mit Verkäufen ausbauen"], next_steps=["Produkt verbessern", "Content ausbauen"])
        if not call.context.get("metrics"):
            return FinalDecision(decision="continue", rationale=SIM + "Keine Marktdaten erhoben – Markttest steht aus; keine Grundlage für Kurswechsel",
                                 lessons=["Veröffentlichung und Messung sind Voraussetzung für jede Bewertung"],
                                 next_steps=["Freigaben prüfen", "Kennzahlen erfassen", "Analyse nach 300 Besuchern wiederholen"])
        return FinalDecision(decision="continue", rationale=SIM + "Erste Daten vorhanden, Aussagekraft gering",
                             lessons=["Mindeststichprobe vorab planen"], next_steps=["Markttest verlängern"])

"""Geschäftszyklen des Unternehmens: Phasen, Aufgabenvorlagen mit Abhängigkeiten und Meilensteine.

Das Unternehmen arbeitet dauerhaft in Zyklen. Am Ende jedes Zyklus entscheidet der CEO anhand
echter Daten, und das Programm startet automatisch den nächsten Zyklus:

- ``launch``  (30 Tage): Nische recherchieren, Idee auswählen, MVP bauen, Markt vorbereiten, testen, auswerten
- ``operate`` (14 Tage): laufender Betrieb – Produkt verbessern, Content/Marketing, Vertrieb, Finanzen, Betrieb
- ``pivot``   (30 Tage): Kurswechsel zur nächstbesten, noch nicht versuchten Idee (ohne neue Grundrecherche)

CEO-Entscheidung → nächster Zyklus: continue → operate, pivot → pivot, stop → launch mit neuer Recherche
(bereits gescheiterte Nischen werden ausgeschlossen).

Die Verantwortungsmatrix ergibt sich direkt aus den Vorlagen (Spalte `agent`). Unabhängige
Aufgaben (z. B. MVP-Bau und Positionierung) laufen parallel; abhängige sequenziell.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from pydantic import BaseModel

from .db import Database
from .tasks import TaskSpec, TaskStatus, TaskStore


class Phase(BaseModel):
    number: int
    name: str
    start_day: int
    end_day: int
    goal: str


PHASES = [
    Phase(number=1, name="Recherche und Auswahl", start_day=1, end_day=5, goal="Eine priorisierte Geschäftsidee auf Basis dokumentierter Kriterien auswählen"),
    Phase(number=2, name="Produktentwicklung", start_day=6, end_day=12, goal="Ein minimales, geprüftes Produkt erstellen"),
    Phase(number=3, name="Marktvorbereitung", start_day=13, end_day=17, goal="Preis, Landingpage, Vertrieb und Compliance vorbereiten"),
    Phase(number=4, name="Markttest", start_day=18, end_day=26, goal="Nach Freigabe veröffentlichen und reale Daten erfassen"),
    Phase(number=5, name="Auswertung", start_day=27, end_day=30, goal="Über Fortführung, Kurswechsel oder Beendigung entscheiden"),
    Phase(number=6, name="Laufender Betrieb", start_day=1, end_day=14, goal="Produkt verbessern, vermarkten, verkaufen, auswerten – und dann neu entscheiden"),
]


def T(key, agent, kind, phase, title, goal, desc, deps=(), acceptance=(), priority=50, review_by=None, not_before_day=1, **inputs) -> TaskSpec:
    return TaskSpec(key=key, agent=agent, kind=kind, phase=phase, title=title, goal=goal, description=desc,
                    depends_on=list(deps), acceptance=list(acceptance), priority=priority, review_by=review_by,
                    not_before_day=not_before_day, output_format=kind, inputs=inputs, created_by="ceo")


TEMPLATES: list[TaskSpec] = [
    # Phase 1 – Recherche und Auswahl
    T("p1.research.opportunities", "research", "market_research", 1, "Geschäftsmöglichkeiten recherchieren",
      "Mindestens fünf digitale Nischen mit Problem, Zielgruppe, Wettbewerb, Preisen und Nachfragebelegen untersuchen",
      "Untersuche u. a. digitale Vorlagen/Rechner, Micro-SaaS, automatisierte B2B-Dienste, Recherche-/Berichtsdienste, "
      "KI-Workflow-Werkzeuge und Nischenprodukte. Keine physischen Produkte, geringe Startkosten, hohe Automatisierbarkeit.",
      acceptance=["≥ 5 Möglichkeiten", "jede Aussage vom Typ 'fact' verweist auf eine Quelle", "Quellen mit URL und Zeitpunkt",
                  "Informationslücken dokumentiert"], priority=90),
    T("p1.strategy.evaluate", "strategy", "idea_evaluation", 1, "Geschäftsmodelle vergleichen und bewerten",
      "Alle Möglichkeiten anhand der neun Kriterien bewerten und eine begründete Empfehlung geben",
      "Bewerte jedes Kriterium mit 0–1 und Beleg. Die Gesamtpunktzahl berechnet das Programm.",
      deps=["p1.research.opportunities"], acceptance=["≥ 3 Ideen bewertet", "alle 9 Kriterien je Idee", "Empfehlung verweist auf bewertete Idee"], priority=85),
    T("p1.finance.unit_economics", "finance", "finance_assessment", 1, "Wirtschaftlichkeit der Top-Ideen bewerten",
      "Kosten, Preise und drei Szenarien für die besten Ideen annehmen",
      "Liefere Annahmen; Break-even und Margen berechnet das Programm.",
      deps=["p1.strategy.evaluate"], acceptance=["drei Szenarien je Idee", "empfohlene Idee enthalten"], priority=80),
    T("p1.qa.selection_review", "qa", "qa_review", 1, "Unabhängiger Review von Recherche und Bewertung",
      "Quellen, Belege, Bewertungen und Risiken unabhängig prüfen",
      "Markiere unbelegte Behauptungen, Datenschutz- und Rechtsrisiken; schlage Korrekturen und Tests vor.",
      deps=["p1.strategy.evaluate", "p1.finance.unit_economics"], acceptance=["Urteil mit Begründung"], priority=80,
      review_target="p1.strategy.evaluate"),
    T("p1.ceo.select_idea", "ceo", "ceo_decision", 1, "Geschäftsidee auswählen",
      "Eine Idee anhand der Scorecards, des Finance- und QA-Reviews auswählen oder gezielt Informationen nachfordern",
      "Die Auswahl wird zusätzlich durch Programmregeln geprüft (Mindestpunktzahl, Reviews, Risiken).",
      deps=["p1.finance.unit_economics", "p1.qa.selection_review"], acceptance=["Auswahl erfüllt die Programmregeln"], priority=95),
    # Phase 2 – Produktentwicklung
    T("p2.product.mvp_spec", "product", "mvp_spec", 2, "MVP definieren",
      "Anforderungen, Prioritäten, Akzeptanzkriterien und Nutzerabläufe für eine minimale erste Version festlegen",
      "Begrenze den Umfang; keine Speicherung personenbezogener Daten im MVP.",
      deps=["p1.ceo.select_idea"], acceptance=["≥ 1 must-Feature mit Akzeptanzkriterien", "Validierungsplan"], priority=80, review_by="ceo"),
    T("p2.builder.product", "builder", "build", 2, "MVP bauen",
      "Das MVP als statische, wartbare Anwendung im Ordner product/ umsetzen", "Nur erlaubte Dateitypen, keine externen Skripte.",
      deps=["p2.product.mvp_spec"], acceptance=["index.html vorhanden", "statische Prüfungen bestanden", "must-Features abgedeckt"],
      priority=75, target_dir="product"),
    T("p2.qa.product_test", "qa", "qa_review", 2, "MVP testen",
      "Funktionen gegen Akzeptanzkriterien prüfen und Sicherheitsprobleme identifizieren",
      "Automatische Prüfungen werden vom Programm ausgeführt und mitgeliefert.",
      deps=["p2.builder.product"], acceptance=["Urteil pass oder pass_with_issues"], priority=75, review_target="p2.builder.product"),
    # Phase 3 – Marktvorbereitung
    T("p3.marketing.positioning", "marketing", "positioning", 3, "Positionierung und Landingpage-Texte",
      "Marke, Wertversprechen, Botschaften, Landingpage-Texte, Redaktionsplan, SEO und Kanäle entwickeln",
      "Keine erfundenen Testimonials oder unbelegten Erfolgsversprechen.",
      deps=["p2.product.mvp_spec"], acceptance=["Landingpage-Texte vollständig", "≥ 1 messbare Hypothese"], priority=60, review_by="ceo"),
    T("p3.finance.pricing", "finance", "finance_assessment", 3, "Preis festlegen",
      "Preis und Szenarien für die ausgewählte Idee festlegen", "Berücksichtige Budget und Zahlungsgebühren.",
      deps=["p3.marketing.positioning"], acceptance=["Szenarien für ausgewählte Idee"], priority=60),
    T("p3.builder.landing", "builder", "build", 3, "Landingpage bauen",
      "Statische Landingpage mit Impressum- und Datenschutz-Seite im Ordner site/ erstellen",
      "Kein Tracking, keine externen Ressourcen, Platzhalter für Pflichtangaben klar kennzeichnen.",
      deps=["p3.marketing.positioning", "p3.finance.pricing", "p2.qa.product_test"],
      acceptance=["index.html, impressum.html, datenschutz.html vorhanden", "statische Prüfungen bestanden"], priority=55, target_dir="site"),
    T("p3.sales.acquisition", "sales", "sales_plan", 3, "Kundengewinnung planen",
      "Kanäle, Customer Journey, erlaubte Leadquellen, Outreach-Entwürfe und KPIs entwickeln",
      "Keine Massen-/Kaltakquise ohne Rechtsgrundlage.",
      deps=["p3.marketing.positioning", "p3.finance.pricing"], acceptance=["Leadquellen mit Rechtsgrundlage", "KPIs"], priority=55, review_by="ceo"),
    T("p3.qa.compliance", "qa", "qa_review", 3, "Datenschutz- und Rechtsprüfung",
      "Landingpage, Texte und Vertriebsplan auf Datenschutz, Pflichtangaben und unzulässige Behauptungen prüfen",
      "Benenne notwendige Freigaben.", deps=["p3.builder.landing", "p3.sales.acquisition"],
      acceptance=["Urteil pass oder pass_with_issues"], priority=55, review_target="p3.builder.landing"),
    T("p3.ops.launch_prep", "operations", "ops_plan", 3, "Markttest vorbereiten",
      "Runbook, wiederkehrende Aufgaben, Monitoring und notwendige Freigabeanträge für den Launch vorbereiten",
      "Externe Aktionen nur als Antrag.", deps=["p3.qa.compliance"], acceptance=["Runbook", "Freigabeanträge vollständig"],
      priority=50, review_by="ceo"),
    # Phase 4 – Markttest
    T("p4.analytics.measurement", "analytics", "analytics_review", 4, "Messplan und Ausgangslage",
      "Kennzahlen, Hypothesen und Mindeststichproben festlegen; vorhandene Ist-Daten auswerten",
      "Nur tatsächlich vorhandene Kennzahlen verwenden.", deps=["p3.ops.launch_prep"], acceptance=["keine erfundenen Kennzahlen"],
      priority=50),
    T("p4.marketing.experiments", "marketing", "experiment_plan", 4, "Marketingexperimente vorbereiten",
      "Messbare Experimente und Inhaltsentwürfe erstellen; Veröffentlichungen beantragen",
      "Jede Veröffentlichung und jede Ausgabe nur als Freigabeantrag.", deps=["p4.analytics.measurement"],
      acceptance=["≥ 1 Experiment mit Mindeststichprobe"], priority=50),
    T("p4.analytics.midtest", "analytics", "analytics_review", 4, "Zwischenauswertung Markttest",
      "Reale Ergebnisse mit Hypothesen vergleichen, unwirksame Maßnahmen benennen", "Statistische Aussagekraft einordnen.",
      deps=["p4.marketing.experiments"], acceptance=["keine erfundenen Kennzahlen"], priority=50, not_before_day=22),
    # Phase 5 – Auswertung
    T("p5.analytics.final", "analytics", "analytics_review", 5, "Abschlussanalyse",
      "Alle Ergebnisse mit den ursprünglichen Hypothesen vergleichen", "Nur echte Messwerte.",
      deps=["p4.analytics.midtest"], acceptance=["keine erfundenen Kennzahlen"], priority=50, not_before_day=27),
    T("p5.finance.final", "finance", "finance_assessment", 5, "Wirtschaftlichkeit neu bewerten",
      "Prognosen mit Ist-Zahlen abgleichen", "Ist-Zahlen klar von Prognosen trennen.",
      deps=["p5.analytics.final"], acceptance=["Abgleich Ist vs. Prognose"], priority=50, not_before_day=27),
    T("p5.ceo.final_decision", "ceo", "final_decision", 5, "Fortführung, Kurswechsel oder Beendigung",
      "Auf Basis der Analysen über das weitere Vorgehen entscheiden", "Begründung mit Kriterien.",
      deps=["p5.analytics.final", "p5.finance.final"], acceptance=["Entscheidung mit Begründung"], priority=60, not_before_day=27),
]

# Laufender Betrieb: jede Abteilung erledigt ihre wiederkehrende Arbeit, danach entscheidet der CEO neu
OPERATE_TEMPLATES: list[TaskSpec] = [
    T("o.analytics.review", "analytics", "analytics_review", 6, "Kennzahlen der letzten Wochen auswerten",
      "Besucher, Anfragen, Verkäufe und Umsatz mit den Zielen vergleichen; Schwachstellen und nächste Experimente benennen",
      "Nur echte Messwerte; ohne Daten klar 'keine Daten' melden.", acceptance=["keine erfundenen Kennzahlen"], priority=80),
    T("o.product.improvements", "product", "mvp_spec", 6, "Produktverbesserungen planen",
      "Aus Feedback und Kennzahlen die wichtigsten Verbesserungen für die nächste Produktversion festlegen",
      "Maximal 5 must-Punkte; Wirkung auf Umsatz/Conversion begründen.", deps=["o.analytics.review"],
      acceptance=["≥ 1 must-Feature mit Akzeptanzkriterien"], priority=70, review_by="ceo"),
    T("o.builder.update", "builder", "build", 6, "Neue Produktversion bauen",
      "Die geplanten Verbesserungen im Produkt umsetzen", "Nur erlaubte Dateitypen, keine externen Skripte.",
      deps=["o.product.improvements"], acceptance=["index.html vorhanden", "statische Prüfungen bestanden"], priority=65,
      target_dir="product"),
    T("o.qa.update_test", "qa", "qa_review", 6, "Neue Produktversion testen",
      "Verbesserungen gegen Akzeptanzkriterien prüfen, Regressionen und Sicherheitsprobleme finden", "",
      deps=["o.builder.update"], acceptance=["Urteil pass oder pass_with_issues"], priority=65, review_target="o.builder.update"),
    T("o.marketing.content", "marketing", "experiment_plan", 6, "Content und Kampagnen planen",
      "Inhalte und Experimente für die nächsten zwei Wochen erstellen; Veröffentlichungen beantragen",
      "Keine unbelegten Versprechen; jede Veröffentlichung nur als Freigabeantrag.", deps=["o.analytics.review"],
      acceptance=["≥ 1 Experiment mit Mindeststichprobe"], priority=60),
    T("o.sales.pipeline", "sales", "sales_plan", 6, "Vertrieb und Kundenanfragen bearbeiten",
      "Anfragen nachfassen, Einwände auswerten, Akquiseweg verbessern", "Kontakt nur mit Rechtsgrundlage.",
      deps=["o.analytics.review", "o.marketing.content"], acceptance=["Leadquellen mit Rechtsgrundlage", "KPIs"], priority=60),
    T("o.ops.release", "operations", "ops_plan", 6, "Betrieb prüfen und Release vorbereiten",
      "Abläufe, Monitoring und Kosten prüfen; Veröffentlichung der neuen Version beantragen", "Externe Aktionen nur als Antrag.",
      deps=["o.qa.update_test"], acceptance=["Runbook"], priority=55, target_dir="product"),
    T("o.finance.review", "finance", "finance_assessment", 6, "Monatsabschluss und Prognose",
      "Ist-Zahlen mit der Prognose abgleichen, Preis und Kosten überprüfen", "Ist und Prognose klar trennen.",
      deps=["o.analytics.review"], acceptance=["Abgleich Ist vs. Prognose"], priority=55, not_before_day=10),
    T("o.ceo.decision", "ceo", "final_decision", 6, "Zyklusentscheidung: weiter, Kurswechsel oder neue Nische",
      "Auf Basis von Analytics, Finanzen, Produkt und Vertrieb über den nächsten Zyklus entscheiden", "Begründung mit Kriterien.",
      deps=["o.finance.review", "o.ops.release", "o.sales.pipeline"], acceptance=["Entscheidung mit Begründung"], priority=60,
      not_before_day=14),
]

CYCLE_TYPES = {
    "launch": {"label": "Gründung / neue Nische", "days": 30, "phases": [1, 2, 3, 4, 5]},
    "pivot": {"label": "Kurswechsel zur nächsten Idee", "days": 30, "phases": [1, 2, 3, 4, 5]},
    "operate": {"label": "Laufender Betrieb", "days": 14, "phases": [6]},
}
NEXT_CYCLE = {"continue": "operate", "pivot": "pivot", "stop": "launch"}

MILESTONES = {
    "launch": [
        ("M1", 1, "Geschäftsidee ausgewählt", ["p1.ceo.select_idea"]),
        ("M2", 2, "MVP gebaut und von QA bestätigt", ["p2.qa.product_test"]),
        ("M3", 3, "Marktvorbereitung abgeschlossen", ["p3.ops.launch_prep"]),
        ("M4", 4, "Markttest ausgewertet", ["p4.analytics.midtest"]),
        ("M5", 5, "Zyklusentscheidung getroffen", ["p5.ceo.final_decision"]),
    ],
    "operate": [
        ("B1", 6, "Kennzahlen ausgewertet", ["o.analytics.review"]),
        ("B2", 6, "Neue Produktversion getestet", ["o.qa.update_test"]),
        ("B3", 6, "Marketing und Vertrieb geplant", ["o.marketing.content", "o.sales.pipeline"]),
        ("B4", 6, "Zyklusentscheidung getroffen", ["o.ceo.decision"]),
    ],
}
MILESTONES["pivot"] = MILESTONES["launch"]
FINAL_TASK = {"launch": "p5.ceo.final_decision", "pivot": "p5.ceo.final_decision", "operate": "o.ceo.decision"}


def cycle_key(key: str, cycle: int) -> str:
    """Zyklus 1 nutzt die Basis-Keys, spätere Zyklen ein Präfix (Duplikatschutz je Zyklus)."""
    return key if cycle <= 1 else f"c{cycle}.{key}"


def templates_for(cycle_type: str) -> list[TaskSpec]:
    if cycle_type == "operate":
        return OPERATE_TEMPLATES
    if cycle_type == "pivot":  # keine neue Grundrecherche: Strategy bewertet die vorhandene Recherche neu
        out = []
        for spec in TEMPLATES:
            if spec.key == "p1.research.opportunities":
                continue
            if spec.key == "p1.strategy.evaluate":
                spec = spec.model_copy(update={"depends_on": [], "title": "Nächstbeste Idee neu bewerten (Kurswechsel)",
                                               "description": spec.description + " Bereits versuchte Ideen sind ausgeschlossen."})
            out.append(spec)
        return out
    return TEMPLATES


def seed(tasks: TaskStore, run_id: str | None = None, *, cycle: int = 1, cycle_type: str = "launch",
         extra_inputs: dict | None = None) -> int:
    created = 0
    for spec in templates_for(cycle_type):
        inputs = {**spec.inputs, **(extra_inputs or {}), "cycle_type": cycle_type}
        if "review_target" in inputs:
            inputs["review_target"] = cycle_key(inputs["review_target"], cycle)
        s = spec.model_copy(update={
            "key": cycle_key(spec.key, cycle), "depends_on": [cycle_key(d, cycle) for d in spec.depends_on],
            "inputs": inputs, "cycle": cycle,
        })
        _, new = tasks.create(s, run_id=run_id)
        created += int(new)
    return created


class ExperimentClock:
    """Tag innerhalb des aktuellen Zyklus. Kalender: echte Tage seit Zyklusstart. Beschleunigt: pro Lauf N Tage."""

    def __init__(self, db: Database, *, mode: str, days: int, days_per_run: int):
        self.db, self.mode, self.default_days, self.days_per_run = db, mode, days, days_per_run

    @property
    def days(self) -> int:
        return CYCLE_TYPES[self.db.get_meta("cycle_type", "launch") or "launch"]["days"]

    def start(self) -> None:
        if not self.db.get_meta("experiment_start"):
            self.db.set_meta("experiment_start", date.today().isoformat())
            self.start_cycle(1, "launch", runs=0)

    def start_cycle(self, cycle: int, cycle_type: str, *, runs: int = 1) -> None:
        self.db.set_meta("cycle", str(cycle))
        self.db.set_meta("cycle_type", cycle_type)
        self.db.set_meta("cycle_start", date.today().isoformat())
        self.db.set_meta("cycle_runs", str(runs))

    def started(self) -> bool:
        return self.db.get_meta("experiment_start") is not None

    def cycle(self) -> int:
        return int(self.db.get_meta("cycle", "1") or 1)

    def cycle_type(self) -> str:
        return self.db.get_meta("cycle_type", "launch") or "launch"

    def advance_run(self) -> None:
        self.db.set_meta("cycle_runs", str(int(self.db.get_meta("cycle_runs", "0") or 0) + 1))

    def day(self) -> int:
        start = self.db.get_meta("cycle_start")
        if not start:
            return 0
        if self.mode == "accelerated":
            runs = int(self.db.get_meta("cycle_runs", "0") or 0)
            return min(self.days, 1 + max(0, runs - 1) * self.days_per_run)
        delta = (datetime.now(timezone.utc).date() - date.fromisoformat(start)).days
        return min(self.days, delta + 1)

    def company_day(self) -> int:
        """Tage seit Gründung (über alle Zyklen)."""
        start = self.db.get_meta("experiment_start")
        if not start:
            return 0
        return (datetime.now(timezone.utc).date() - date.fromisoformat(start)).days + 1


PHASE_BY_NUMBER = {p.number: p for p in PHASES}


def phases_for(cycle_type: str) -> list[Phase]:
    return [PHASE_BY_NUMBER[n] for n in CYCLE_TYPES[cycle_type]["phases"]]


def phase_for_day(day: int, cycle_type: str = "launch") -> Phase:
    phases = phases_for(cycle_type)
    for p in phases:
        if p.start_day <= day <= p.end_day:
            return p
    return phases[0] if day < 1 else phases[-1]


def work_phase(tasks: list, cycle_type: str = "launch") -> Phase:
    """Tatsächliche Arbeitsphase: die niedrigste Phase mit unerledigten Aufgaben im aktuellen Zyklus."""
    open_phases = [t.phase for t in tasks if t.status != TaskStatus.COMPLETED]
    if not open_phases:
        return phases_for(cycle_type)[-1]
    return PHASE_BY_NUMBER[min(open_phases)]


def milestones(tasks_by_key: dict, cycle: int = 1, cycle_type: str = "launch") -> list[dict]:
    out = []
    for mid, phase, title, keys in MILESTONES[cycle_type]:
        ckeys = [cycle_key(k, cycle) for k in keys]
        ts = [tasks_by_key.get(k) for k in ckeys]
        done = all(t is not None and t.status == TaskStatus.COMPLETED for t in ts)
        out.append({"id": mid, "phase": phase, "title": title, "achieved": done,
                    "achieved_at": max((t.completed_at or "") for t in ts) if done else None, "tasks": ckeys})
    return out


def progress(tasks: list) -> dict:
    """Fortschritt = abgeschlossene Aufgaben des aktuellen Zyklus / alle Aufgaben des aktuellen Zyklus."""
    total = len(tasks)
    done = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
    return {"completed": done, "total": total, "percent": round(done / total * 100, 1) if total else None,
            "formula": "abgeschlossene Aufgaben / alle Aufgaben des aktuellen Zyklus"}

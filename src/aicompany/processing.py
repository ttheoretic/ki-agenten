"""Inhaltliche Validierung und Weiterverarbeitung der Agentenergebnisse.

`validate(...)` liefert eine Liste von Fehlern (leer = gültig). Ungültige Ergebnisse gehen mit
konkretem Feedback zur Überarbeitung zurück (begrenzt durch max_revisions_per_task).
"""
from __future__ import annotations

import json
from pathlib import PurePosixPath
from typing import Any

from pydantic import BaseModel

from .agents import schemas as S
from .checks import check_claims
from .security import PermissionDenied, Sandbox, SecurityPolicy


def _norm_url(u: str) -> str:
    return u.split("#")[0].rstrip("/").lower()


def validate(kind: str, output: BaseModel, *, ctx: dict[str, Any], policy: SecurityPolicy, sandbox: Sandbox,
             agent: str, cited_urls: list[str], simulated: bool) -> tuple[list[str], dict]:
    """Gibt (Fehler, abgeleitete Prüfdaten) zurück."""
    errors: list[str] = []
    derived: dict[str, Any] = {}

    if isinstance(output, S.ResearchReport):
        minimum = 1 if ctx.get("followup") else 5
        if len(output.opportunities) < minimum:
            errors.append(f"Nur {len(output.opportunities)} Möglichkeiten – mindestens {minimum} gefordert")
        src_ids = {s.id for s in output.sources}
        for s in output.sources:
            if not s.url.startswith(("http://", "https://")):
                errors.append(f"Quelle {s.id} hat keine gültige URL")
        for o in output.opportunities:
            for c in o.demand_evidence + o.willingness_to_pay_evidence:
                if c.kind == "fact" and not c.source_ids:
                    errors.append(f"Fakt ohne Quelle bei '{o.name}': {c.statement[:80]}")
                unknown = [sid for sid in c.source_ids if sid not in src_ids]
                if unknown:
                    errors.append(f"Unbekannte Quellen-IDs {unknown} bei '{o.name}'")
        if not output.information_gaps:
            errors.append("Informationslücken müssen dokumentiert werden")
        # Quellenabgleich mit den tatsächlich von der Websuche gelieferten URLs
        cited = {_norm_url(u) for u in cited_urls}
        verification = []
        for s in output.sources:
            verified = _norm_url(s.url) in cited if cited else False
            verification.append({"id": s.id, "url": s.url, "verified_by_search": verified})
        derived["source_verification"] = verification
        derived["web_search_used"] = bool(cited)
        if cited and not simulated:
            unverified = [v for v in verification if not v["verified_by_search"]]
            if len(unverified) > len(verification) / 2:
                errors.append(f"{len(unverified)} von {len(verification)} Quellen stammen nicht aus der Websuche – mögliche erfundene Quellen")

    elif isinstance(output, S.IdeaEvaluation):
        if len(output.ideas) < 3:
            errors.append("Mindestens 3 Ideen müssen bewertet werden")
        for idea in output.ideas:
            crits = [c.criterion for c in idea.criteria]
            missing = set(S.CRITERIA) - set(crits)
            if missing or len(crits) != len(set(crits)):
                errors.append(f"Idee {idea.idea_id}: Kriterien unvollständig oder doppelt (fehlend: {sorted(missing)})")
        if output.recommendation.idea_id not in {i.idea_id for i in output.ideas}:
            errors.append("Empfehlung verweist auf keine bewertete Idee")

    elif isinstance(output, S.FinanceAssessment):
        if not output.ideas:
            errors.append("Keine Ideen bewertet")
        for i in output.ideas:
            names = sorted(s.name for s in i.scenarios)
            if names != ["base", "conservative", "optimistic"]:
                errors.append(f"Idee {i.idea_id}: genau drei Szenarien (konservativ, mittel, optimistisch) gefordert")
        sel = ctx.get("selected_idea")
        if sel and not any(i.idea_id == sel["id"] for i in output.ideas):
            errors.append(f"Ausgewählte Idee {sel['id']} fehlt in der Finanzbewertung")
        rec = (ctx.get("recommended_idea") or None)
        if not sel and rec and not any(i.idea_id == rec for i in output.ideas):
            errors.append(f"Empfohlene Idee {rec} fehlt in der Finanzbewertung")
        if not ctx.get("metrics") and "keine" not in output.actuals_vs_forecast.lower():
            errors.append("Es liegen keine Ist-Daten vor – actuals_vs_forecast darf keine Ist-Zahlen behaupten")

    elif isinstance(output, S.QAReview):
        if output.verdict == "fail" and not output.issues:
            errors.append("Ein 'fail'-Urteil braucht mindestens einen konkreten Befund")
        for issue in output.issues:
            if not issue.suggested_fix.strip():
                errors.append("Jeder Befund braucht einen konkreten Korrekturvorschlag")

    elif isinstance(output, S.MVPSpec):
        musts = [f for f in output.features if f.priority == "must"]
        if not musts or any(not f.acceptance_criteria for f in musts):
            errors.append("Mindestens ein must-Feature mit Akzeptanzkriterien erforderlich")
        if len(musts) > 5:
            errors.append("Zu viele must-Features für ein MVP (max. 5) – Umfang begrenzen")
        if not output.validation_plan:
            errors.append("Validierungsplan fehlt")

    elif isinstance(output, S.BuildResult):
        target = ctx.get("target_dir", "product")
        limits = policy.limits
        if not output.files:
            errors.append("Keine Dateien geliefert")
        if len(output.files) > limits.max_files_per_build:
            errors.append(f"Zu viele Dateien ({len(output.files)} > {limits.max_files_per_build})")
        paths = []
        for f in output.files:
            p = PurePosixPath(f.path)
            try:
                sandbox.check_write(agent, f"{target}/{f.path}")
                sandbox.resolve(f"{target}/{f.path}")
                if ".." in p.parts or p.is_absolute():
                    raise PermissionDenied(f.path)
            except PermissionDenied as exc:
                errors.append(f"SICHERHEIT: unzulässiger Pfad {f.path} ({exc})")
                derived["security_violation"] = True
                continue
            if p.suffix.lower() not in limits.allowed_build_extensions:
                errors.append(f"Dateityp nicht erlaubt: {f.path}")
                continue
            if len(f.content.encode()) > limits.max_file_bytes:
                errors.append(f"Datei zu groß: {f.path}")
            paths.append(f.path)
        if "index.html" not in paths:
            errors.append("index.html fehlt")
        if target == "site":
            for req in ("impressum.html", "datenschutz.html"):
                if req not in paths:
                    errors.append(f"{req} fehlt (Pflichtseite)")
        spec = ctx.get("mvp_spec")
        if spec and target == "product":
            musts = {f["id"] for f in spec.get("features", []) if f["priority"] == "must"}
            missing = musts - set(output.feature_coverage)
            if missing:
                errors.append(f"must-Features nicht umgesetzt: {sorted(missing)}")

    elif isinstance(output, S.Positioning):
        if not output.landing_page.headline or not output.landing_page.sections:
            errors.append("Landingpage-Texte unvollständig")
        if not output.hypotheses:
            errors.append("Mindestens eine messbare Hypothese erforderlich")
        claims = check_claims(output.model_dump_json())
        if claims:
            errors.append(f"Unzulässige Werbeaussagen: {claims}")

    elif isinstance(output, S.SalesPlan):
        for ls in output.lead_sources:
            if len(ls.legal_basis.strip()) < 5:
                errors.append(f"Leadquelle '{ls.source}' ohne Rechtsgrundlage")
        claims = check_claims(output.model_dump_json())
        if claims:
            errors.append(f"Unzulässige Werbeaussagen: {claims}")
        if not output.kpis:
            errors.append("KPIs fehlen")

    elif isinstance(output, S.OpsPlan):
        if not output.runbook:
            errors.append("Runbook fehlt")

    elif isinstance(output, S.ExperimentPlan):
        if not output.experiments or any(e.min_sample_size <= 0 for e in output.experiments):
            errors.append("Experimente brauchen eine Mindeststichprobe > 0")
        claims = check_claims(output.model_dump_json())
        if claims:
            errors.append(f"Unzulässige Werbeaussagen: {claims}")

    elif isinstance(output, S.AnalyticsReview):
        real = {(m["name"], round(float(m["value"]), 6)) for m in ctx.get("metrics", [])}
        for m in output.metrics_used:
            if (m.name, round(m.value, 6)) not in real:
                errors.append(f"Kennzahl '{m.name}={m.value}' existiert nicht in den Messdaten – erfundene Kennzahlen sind unzulässig")
        if not real:
            if output.data_available:
                errors.append("data_available=true, obwohl keine Messdaten vorliegen")
            if any(h.status in ("supported", "rejected") for h in output.hypothesis_results):
                errors.append("Ohne Messdaten kann keine Hypothese bestätigt oder widerlegt werden")

    elif isinstance(output, S.FinalDecision):
        if not output.rationale.strip():
            errors.append("Begründung fehlt")

    if hasattr(output, "external_actions"):
        for a in output.external_actions:  # type: ignore[attr-defined]
            try:
                json.loads(a.params_json)
            except json.JSONDecodeError:
                errors.append(f"Parameter des Antrags '{a.title}' sind kein gültiges JSON")
    return errors, derived


def summarize_markdown(title: str, agent: str, output: BaseModel, derived: dict, simulated: bool) -> str:
    head = f"# {title}\n\nVerantwortlich: {agent}\n"
    if simulated:
        head += "\n> **DRY-RUN:** Inhalt wurde simuliert und ist keine echte Recherche oder Analyse.\n"
    body = "```json\n" + json.dumps(output.model_dump(), ensure_ascii=False, indent=2) + "\n```\n"
    extra = ("\n## Vom Programm berechnet\n\n```json\n" + json.dumps(derived, ensure_ascii=False, indent=2) + "\n```\n") if derived else ""
    return head + "\n" + body + extra

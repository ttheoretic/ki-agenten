"""Managementberichte – deterministisch aus der Datenbank erzeugt (keine API-Kosten, keine erfundenen Zahlen)."""
from __future__ import annotations

from datetime import datetime, timezone

from .agents.roles import ROLES
from .db import now_iso


def build_report(company, *, title: str = "Managementbericht", run_id: str | None = None) -> str:
    from .state import company_snapshot  # spät importieren (Zyklus vermeiden)

    s = company_snapshot(company)
    b = s["budget"]
    lines = [f"# {title}", "", f"Erstellt: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  ", f"Modus: **{s['mode_label']}**  "]
    if run_id:
        lines.append(f"Lauf: `{run_id}`  ")
    if s["simulated"]:
        lines += ["", "> **Hinweis:** Dry-Run – alle Agentenergebnisse und Kosten sind simuliert."]
    exp = s["experiment"]
    lines += ["", "## Gesamtstatus", "", f"- Ziel: {s['company']['goal']}", f"- Unternehmensstatus: **{s['company']['status']}**",
              f"- Zyklus {exp['cycle']} ({exp['cycle_label']}), Tag {exp['day']}/{exp['days']} – Arbeitsphase: {exp['work_phase']['name']}",
              f"- Bisherige Zyklen: " + (", ".join(f"{c['cycle']}: {c['label']}" + (f" → {c['decision']}" if c.get('decision') else "")
                                                   for c in exp['cycles']) or "–"),
              f"- Verworfene Ideen: {', '.join(exp['tried_ideas']) or 'keine'}",
              f"- Fortschritt: {s['progress']['completed']}/{s['progress']['total']} Aufgaben ({s['progress']['percent']} %) – "
              f"Formel: {s['progress']['formula']}"]
    idea = s["selected_idea"]
    lines += ["", "## Geschäftsmodell", ""]
    if idea:
        lines.append(f"**{idea['name']}** – {idea['score']} Punkte. Begründung: {idea['rationale']}")
    else:
        lines.append("Noch keine Geschäftsidee ausgewählt.")
    if s["ideas"]:
        lines += ["", "| Idee | Punkte | Status |", "|---|---|---|"]
        lines += [f"| {i['name']} | {i['score']} | {i['status']} |" for i in s["ideas"]]
    lines += ["", "## Meilensteine", ""]
    lines += [f"- [{'x' if m['achieved'] else ' '}] {m['id']} {m['title']}" for m in s["milestones"]]
    lines += ["", "## Budget und Kosten", "", f"- API-Kosten diesen Monat: {b['api_spent_eur']:.4f} € von {b['api_limit_eur']:.2f} €",
              f"- Gesamtausgaben: {b['total_spent_eur']:.4f} € von {b['total_limit_eur']:.2f} € "
              f"(verbleibend {b['total_remaining_eur']:.2f} €, davon gebunden durch Freigaben {b['external_committed_eur']:.2f} €)",
              f"- Davon konservativ geschätzt (Verbrauch unbekannt): {b['estimated_share_eur']:.4f} €"]
    for a in company.budget.by_agent():
        lines.append(f"  - {a['agent']} / {a['model']}: {a['calls']} Aufrufe, {a['cost_eur']:.4f} €")
    fa = s["finance_actuals"]
    lines += ["", "## Einnahmen und Kennzahlen", "",
              f"- Umsatz: {fa['revenue_eur']:.2f} €" if fa["has_revenue_data"] else "- Umsatz: Noch keine Daten"]
    if s["metrics"]:
        lines += [f"- {m['name']}: {m['value']} {m['unit']} (Quelle: {m['source']}, {m['ts'][:10]})" for m in s["metrics"][:15]]
    else:
        lines.append("- Kennzahlen: Noch keine Daten (Messwerte werden im Control-Center erfasst)")
    lines += ["", "## Letzte CEO-Entscheidungen", ""]
    lines += [f"- {d['ts'][:16]}: {d['summary']}" for d in s["decisions"]] or ["- keine"]
    open_ap = [a for a in s["approvals"] if a["status"] in ("pending", "info_requested", "deferred")]
    lines += ["", "## Offene Freigaben", ""]
    lines += [f"- {a['id']}: {a['title']} ({a['action_type']}, {a['cost_eur']:.2f} €) – {ROLES[a['agent']].name}" for a in open_ap] or ["- keine"]
    lines += ["", "## Risiken und Blockaden", ""]
    lines += [f"- ({r['severity']}) {r['description']} → {r['suggested_fix']}" for r in s["risks"][:10]]
    lines += [f"- BLOCKIERT: {bl['title']} – {bl['error']}" for bl in s["blockers"]]
    if not s["risks"] and not s["blockers"]:
        lines.append("- keine offenen")
    lines += ["", "## Nächste geplante Schritte", ""]
    lines += [f"- {t['title']} ({ROLES[t['agent']].name})" for t in s["next_steps"]] or ["- keine ausführbaren Aufgaben"]
    if s.get("ceo_next_step"):
        lines.append(f"- CEO: {s['ceo_next_step']}")
    return "\n".join(lines) + "\n"


def write_report(company, *, run_id: str | None = None, title: str = "Managementbericht") -> str:
    text = build_report(company, title=title, run_id=run_id)
    rel = f"reports/bericht-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')}.md"
    company.sandbox.write_text("ceo", rel, text, company.redactor)
    company.db.execute(
        "INSERT OR REPLACE INTO artifacts(path, task_id, agent, kind, sha256, size, created_at) VALUES (?,?,?,?,?,?,?)",
        (rel, None, "ceo", "report", None, len(text.encode()), now_iso()),
    )
    company.events.emit("report.created", f"{title} erstellt", agent="ceo", run_id=run_id, data={"path": rel})
    return rel

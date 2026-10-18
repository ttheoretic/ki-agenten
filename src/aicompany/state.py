"""Zustands-Snapshot für Control-Center und Berichte – ausschließlich aus echten Backend-Daten abgeleitet."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from .agents.roles import GROUPS, ROLES
from .company import Company
from .db import loads
from .events import COMM_TYPES
from .preflight import selftest_status
from .tasks import Task, TaskStatus
from .workflow import PHASES, milestones, phase_for_day, progress, work_phase

TS = TaskStatus

STATUS_LABELS = {
    "ready": "Bereit", "working": "Arbeitet", "researching": "Recherchiert", "communicating": "Kommuniziert",
    "waiting_result": "Wartet auf Ergebnis", "waiting_approval": "Wartet auf Freigabe", "reviewing": "Prüft Ergebnis",
    "blocked": "Blockiert", "error": "Fehler aufgetreten", "done": "Abgeschlossen", "idle": "Keine Aufgaben", "paused": "Pausiert",
}


def task_brief(t: Task) -> dict:
    return {"id": t.id, "key": t.key, "title": t.title, "agent": t.agent, "kind": t.kind, "phase": t.phase, "status": t.status.value,
            "priority": t.priority, "revision_count": t.revision_count, "depends_on": t.depends_on, "review_by": t.review_by,
            "not_before_day": t.not_before_day, "error": t.error, "est_cost_eur": round(t.est_cost_eur, 5),
            "actual_cost_eur": round(t.actual_cost_eur, 5), "artifacts": t.artifacts, "updated_at": t.updated_at,
            "started_at": t.started_at, "completed_at": t.completed_at, "created_by": t.created_by}


def _last_activity(company: Company) -> dict[str, dict]:
    rows = company.db.query(
        "SELECT e.* FROM events e JOIN (SELECT COALESCE(agent, from_agent) AS a, MAX(id) AS mid FROM events"
        " WHERE COALESCE(agent, from_agent) IS NOT NULL GROUP BY COALESCE(agent, from_agent)) m ON e.id = m.mid"
    )
    return {r["agent"] or r["from_agent"]: dict(r) for r in rows}


def agent_status(agent_id: str, tasks: list[Task], by_key: dict[str, Task], *, paused: bool, open_approvals: int,
                 recent_comm: bool, current_day: int, running: bool) -> str:
    """Status wird ausschließlich aus Aufgaben-, Freigabe- und Ereignisdaten abgeleitet."""
    mine = [t for t in tasks if t.agent == agent_id]
    if paused:
        return "paused"
    active = [t for t in mine if t.status == TS.IN_PROGRESS]
    if active and running:
        t = active[0]
        if t.kind in ("qa_review", "ceo_review"):
            return "reviewing"
        if t.kind == "market_research":
            return "researching"
        return "working"
    if agent_id == "ceo" and any(t.status == TS.REVIEW and t.review_by == "ceo" for t in tasks):
        return "reviewing"
    if any(t.status == TS.FAILED for t in mine):
        return "error"
    if open_approvals:
        return "waiting_approval"
    if recent_comm:
        return "communicating"
    if any(t.status == TS.BLOCKED for t in mine):
        return "blocked"
    pending = [t for t in mine if t.status in (TS.PENDING, TS.REVIEW)]
    if pending:
        if any(t.status == TS.PENDING and all(by_key.get(d) and by_key[d].status == TS.COMPLETED for d in t.depends_on)
               and t.not_before_day <= current_day for t in pending):
            return "ready"
        return "waiting_result"
    if mine and all(t.status == TS.COMPLETED for t in mine):
        return "done"
    return "idle"


def active_run(company: Company) -> dict | None:
    stale = (datetime.now(timezone.utc) - timedelta(seconds=company.settings.orchestrator.run_stale_after_seconds)).isoformat()
    row = company.db.query_one("SELECT * FROM runs WHERE status='running' AND heartbeat_at > ? ORDER BY started_at DESC", (stale,))
    return dict(row) if row else None


def agents_overview(company: Company, tasks: list[Task] | None = None) -> list[dict]:
    tasks = tasks if tasks is not None else company.tasks.list()
    by_key = {t.key: t for t in tasks}
    paused = company.control.paused_agents()
    approvals = company.approvals.list("open")
    last = _last_activity(company)
    running = active_run(company) is not None
    recent = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    comm_recent = {r["from_agent"] for r in company.db.query(
        f"SELECT DISTINCT from_agent FROM events WHERE ts > ? AND type IN ({','.join('?' * len(COMM_TYPES))})", (recent, *COMM_TYPES))}
    day = company.clock.day()
    costs = {r["agent"]: r for r in company.db.query(
        "SELECT agent, SUM(cost_eur) AS cost, SUM(input_tokens) AS tin, SUM(output_tokens) AS tout, COUNT(*) AS calls"
        " FROM cost_records WHERE kind='api' GROUP BY agent")}
    out = []
    for aid, role in ROLES.items():
        mine = [t for t in tasks if t.agent == aid]
        current = next((t for t in mine if t.status == TS.IN_PROGRESS), None)
        nxt = next((t for t in sorted(mine, key=lambda t: (t.phase, -t.priority)) if t.status == TS.PENDING), None)
        status = agent_status(aid, tasks, by_key, paused=aid in paused, open_approvals=sum(1 for a in approvals if a.agent == aid),
                              recent_comm=aid in comm_recent, current_day=day, running=running)
        waiting_on = []
        if nxt:
            waiting_on = [d for d in nxt.depends_on if not (by_key.get(d) and by_key[d].status == TS.COMPLETED)]
        done = sum(1 for t in mine if t.status == TS.COMPLETED)
        cost = costs.get(aid)
        out.append({
            "id": aid, "name": role.name, "title": role.title, "group": role.group, "group_label": GROUPS[role.group],
            "status": status, "status_label": STATUS_LABELS[status], "paused": aid in paused,
            "current_task": task_brief(current) if current else None,
            "next_task": task_brief(nxt) if nxt else None,
            "waiting_on": waiting_on,
            "progress": {"completed": done, "total": len(mine)} if mine else None,
            "errors": [{"task_id": t.id, "title": t.title, "error": t.error} for t in mine if t.status in (TS.FAILED, TS.BLOCKED)],
            "open_approvals": [a.id for a in approvals if a.agent == aid],
            "last_activity": {"ts": last[aid]["ts"], "message": last[aid]["message"], "type": last[aid]["type"]} if aid in last else None,
            "model": company.settings.model_for(aid),
            "cost_eur": round(cost["cost"], 5) if cost else 0.0,
            "tokens": {"input": cost["tin"], "output": cost["tout"]} if cost else {"input": 0, "output": 0},
            "calls": cost["calls"] if cost else 0,
        })
    return out


def company_snapshot(company: Company) -> dict:
    s = company.settings
    tasks = [t for t in company.tasks.list()]
    workflow_tasks = [t for t in tasks if not t.key.startswith("ceo.review.")]
    by_key = {t.key: t for t in tasks}
    day = company.clock.day()
    selected = company.db.get_meta("selected_idea")
    last_report = company.db.query_one("SELECT path, created_at FROM artifacts WHERE kind='report' ORDER BY created_at DESC LIMIT 1")
    decisions = [dict(r) | {"data": loads(r["data"], {})} for r in company.db.query("SELECT * FROM decisions ORDER BY id DESC LIMIT 8")]
    metrics = [dict(r) for r in company.db.query("SELECT * FROM metrics ORDER BY ts DESC LIMIT 100")]
    revenue = company.db.query_one("SELECT COALESCE(SUM(value),0) AS s, COUNT(*) AS n FROM metrics WHERE name='revenue_eur' AND source!='demo'")
    risks = []
    for t in tasks:
        if t.kind == "qa_review" and t.result:
            for i in t.result["output"].get("issues", []):
                if i["severity"] in ("medium", "high", "critical"):
                    risks.append({"severity": i["severity"], "description": i["description"], "source_task": t.key,
                                  "suggested_fix": i["suggested_fix"]})
    blockers = [{"task_id": t.id, "title": t.title, "status": t.status.value, "error": t.error, "agent": t.agent}
                for t in tasks if t.status in (TS.FAILED, TS.BLOCKED)]
    wphase = work_phase(workflow_tasks) if workflow_tasks else PHASES[0]
    next_decision = None
    if any(t.status == TS.REVIEW and t.review_by == "ceo" for t in tasks):
        next_decision = "CEO-Review vorgelegter Ergebnisse"
    elif not selected:
        next_decision = "Auswahl der Geschäftsidee (Meilenstein M1)"
    elif company.approvals.list("open"):
        next_decision = "Offene Freigaben des Eigentümers"
    elif by_key.get("p5.ceo.final_decision") and by_key["p5.ceo.final_decision"].status != TS.COMPLETED:
        next_decision = "Abschlussentscheidung (Tag 27–30)"
    budget = company.budget.summary()
    run = active_run(company)
    last_run = company.db.query_one("SELECT * FROM runs ORDER BY started_at DESC LIMIT 1")
    if run:
        status = "running"
    elif company.control.company_status() != "active":
        status = company.control.company_status()
    elif budget["exhausted"]:
        status = "budget_exhausted"
    elif company.db.get_meta("experiment_status") == "finished":
        status = "finished"
    elif blockers:
        status = "attention"
    elif not company.clock.started():
        status = "not_started"
    else:
        status = "idle"
    return {
        "mode": s.mode, "mode_label": company.mode_label(), "simulated": s.mode == "dry_run",
        "company": {"name": s.company.name, "goal": s.company.goal, "status": status, "control": company.control.flags()},
        "experiment": {
            "started": company.clock.started(), "start_date": company.db.get_meta("experiment_start"), "day": day, "days": s.experiment.days,
            "clock": s.experiment.clock, "plan_phase": phase_for_day(day).model_dump() if day else None,
            "work_phase": wphase.model_dump(), "phases": [p.model_dump() for p in PHASES],
            "status": company.db.get_meta("experiment_status", "running" if company.clock.started() else "not_started"),
            "final_decision": company.db.get_meta("final_decision"),
        },
        "selected_idea": json.loads(selected) if selected else None,
        "ideas": [dict(r) | {"data": loads(r["data"], {})} for r in company.db.query("SELECT * FROM ideas ORDER BY score DESC")],
        "progress": progress(workflow_tasks),
        "milestones": milestones(by_key),
        "budget": budget,
        "finance_actuals": {"revenue_eur": float(revenue["s"]) if revenue["n"] else None, "expenses_eur": budget["total_spent_eur"],
                            "has_revenue_data": bool(revenue["n"])},
        "metrics": metrics,
        "risks": risks[:20],
        "blockers": blockers,
        "next_decision": next_decision,
        "ceo_next_step": company.db.get_meta("ceo_next_step"),
        "next_steps": [task_brief(t) for t in company.tasks.ready(current_day=max(day, 1), paused_agents=company.control.paused_agents())][:6],
        "decisions": decisions,
        "last_report": dict(last_report) if last_report else None,
        "active_run": run,
        "last_run": dict(last_run) if last_run else None,
        "agents": agents_overview(company, tasks),
        "groups": GROUPS,
        "tasks": [task_brief(t) for t in tasks],
        "approvals": [a.model_dump() for a in company.approvals.list()],
        "last_event_id": company.events.last_id(),
        "selftest": selftest_status(),
    }


def agent_detail(company: Company, agent_id: str) -> dict:
    role = ROLES[agent_id]
    tasks = company.tasks.list(agent=agent_id)
    overview = next(a for a in agents_overview(company) if a["id"] == agent_id)
    comms = company.events.list(agent=agent_id, types=sorted(COMM_TYPES), limit=30, descending=True)
    warnings = company.events.list(agent=agent_id, severity="warning", limit=20, descending=True)
    perms = company.policy.permissions(agent_id)
    results = [{"task_id": t.id, "title": t.title, "artifacts": t.artifacts, "completed_at": t.completed_at}
               for t in tasks if t.status == TS.COMPLETED]
    return {
        **overview,
        "mission": role.mission, "responsibilities": role.responsibilities, "rules": role.rules,
        "tools": list(perms.tools), "write_dirs": list(perms.write_dirs), "task_kinds": role.task_kinds,
        "limits": company.settings.agent_limits(agent_id).model_dump(),
        "queue": [task_brief(t) for t in tasks if t.status in (TS.PENDING, TS.REVIEW)],
        "completed_tasks": [task_brief(t) for t in tasks if t.status == TS.COMPLETED],
        "failed_tasks": [task_brief(t) for t in tasks if t.status in (TS.FAILED, TS.BLOCKED)],
        "history": [task_brief(t) | {"history": t.history, "feedback": t.feedback} for t in tasks],
        "results": results,
        "communications": [e.model_dump() for e in comms],
        "warnings": [e.model_dump() for e in warnings],
        "next_step": ({"type": "planned", "task": overview["next_task"]} if overview["next_task"] else None),
        "running_action": ({"type": "running", "task": overview["current_task"]} if overview["current_task"] else None),
    }

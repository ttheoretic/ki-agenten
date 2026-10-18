"""Zentraler, persistenter Ereignisstrom.

Agenten, Aufgabenverwaltung, Budgetkontrolle und Freigabezentrum melden alle Statusänderungen
hierüber. Ereignisse liegen in SQLite; der Live-Stream (SSE) liest prozessübergreifend
nach `id > last_id`, deshalb sehen Server und CLI-Läufe denselben Strom.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from .db import Database, dumps, loads, now_iso
from .security import Redactor

# Ereignisarten, die eine echte Kommunikation/Übergabe zwischen zwei Agenten darstellen
COMM_TYPES = {"comm.assignment", "comm.handoff", "comm.message", "comm.feedback"}

SEVERITIES = ("debug", "info", "success", "warning", "error", "critical")


class Event(BaseModel):
    id: int
    ts: str
    type: str
    severity: str
    agent: str | None
    from_agent: str | None
    to_agent: str | None
    task_id: str | None
    run_id: str | None
    approval_id: str | None
    message: str
    data: dict[str, Any]


def row_to_event(row) -> Event:
    return Event(**{**dict(row), "data": loads(row["data"], {})})


class EventBus:
    def __init__(self, db: Database, redactor: Redactor):
        self.db = db
        self.redactor = redactor

    def emit(
        self,
        type: str,
        message: str,
        *,
        agent: str | None = None,
        severity: str = "info",
        from_agent: str | None = None,
        to_agent: str | None = None,
        task_id: str | None = None,
        run_id: str | None = None,
        approval_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> Event:
        if severity not in SEVERITIES:
            severity = "info"
        if type in COMM_TYPES and not (from_agent and to_agent):
            raise ValueError("Kommunikationsereignisse brauchen Absender und Empfänger")
        msg = self.redactor.redact(message)
        payload = self.redactor.redact_obj(data or {})
        ts = now_iso()
        with self.db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO events(ts, type, severity, agent, from_agent, to_agent, task_id, run_id, approval_id, message, data)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (ts, type, severity, agent or from_agent, from_agent, to_agent, task_id, run_id, approval_id, msg, dumps(payload)),
            )
            event_id = cur.lastrowid
        return Event(
            id=event_id, ts=ts, type=type, severity=severity, agent=agent or from_agent, from_agent=from_agent,
            to_agent=to_agent, task_id=task_id, run_id=run_id, approval_id=approval_id, message=msg, data=payload,
        )

    def list(
        self,
        *,
        after_id: int = 0,
        limit: int = 200,
        agent: str | None = None,
        types: list[str] | None = None,
        severity: str | None = None,
        since: str | None = None,
        until: str | None = None,
        task_id: str | None = None,
        descending: bool = False,
    ) -> list[Event]:
        sql = "SELECT * FROM events WHERE id > ?"
        params: list[Any] = [after_id]
        if agent:
            sql += " AND (agent = ? OR from_agent = ? OR to_agent = ?)"
            params += [agent, agent, agent]
        if types:
            clauses = []
            for t in types:
                if t.endswith("*"):
                    clauses.append("type LIKE ?")
                    params.append(t[:-1] + "%")
                else:
                    clauses.append("type = ?")
                    params.append(t)
            sql += " AND (" + " OR ".join(clauses) + ")"
        if severity:
            idx = SEVERITIES.index(severity) if severity in SEVERITIES else 0
            allowed = SEVERITIES[idx:]
            sql += f" AND severity IN ({','.join('?' * len(allowed))})"
            params += list(allowed)
        if since:
            sql += " AND ts >= ?"
            params.append(since)
        if until:
            sql += " AND ts <= ?"
            params.append(until)
        if task_id:
            sql += " AND task_id = ?"
            params.append(task_id)
        sql += " ORDER BY id DESC" if descending else " ORDER BY id ASC"
        sql += " LIMIT ?"
        params.append(max(1, min(limit, 2000)))
        return [row_to_event(r) for r in self.db.query(sql, params)]

    def last_id(self) -> int:
        row = self.db.query_one("SELECT MAX(id) AS m FROM events")
        return int(row["m"] or 0)

    def get(self, event_id: int) -> Event | None:
        row = self.db.query_one("SELECT * FROM events WHERE id = ?", (event_id,))
        return row_to_event(row) if row else None

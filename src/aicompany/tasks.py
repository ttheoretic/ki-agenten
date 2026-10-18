"""Aufgabenverwaltung mit Zustandsmaschine, Duplikatschutz und atomarer Übernahme."""
from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from .db import Database, dumps, loads, now_iso
from .events import EventBus


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"


S = TaskStatus
ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    S.PENDING: {S.IN_PROGRESS, S.BLOCKED, S.FAILED},
    S.IN_PROGRESS: {S.REVIEW, S.PENDING, S.FAILED, S.BLOCKED},
    S.REVIEW: {S.COMPLETED, S.PENDING, S.FAILED},
    S.BLOCKED: {S.PENDING, S.FAILED},
    S.COMPLETED: {S.PENDING},  # nur durch Rückgabe zur Überarbeitung (QA/CEO), begrenzt durch revision_count
    S.FAILED: {S.PENDING},  # nur durch manuellen Retry des Eigentümers
}


class InvalidTransition(Exception):
    pass


class TaskSpec(BaseModel):
    key: str
    agent: str
    kind: str
    title: str
    goal: str
    description: str
    phase: int
    depends_on: list[str] = []  # Aufgaben-Keys
    inputs: dict[str, Any] = {}
    output_format: str
    acceptance: list[str] = []
    priority: int = 50
    review_by: str | None = None
    not_before_day: int = 1
    created_by: str = "system"
    parent_task_id: str | None = None


class Task(BaseModel):
    id: str
    key: str
    agent: str
    kind: str
    title: str
    goal: str
    description: str
    phase: int
    inputs: dict[str, Any]
    depends_on: list[str]
    output_format: str
    acceptance: list[str]
    priority: int
    status: TaskStatus
    review_by: str | None
    not_before_day: int
    revision_count: int
    attempt_count: int
    est_cost_eur: float
    actual_cost_eur: float
    result: dict[str, Any] | None
    artifacts: list[str]
    history: list[dict[str, Any]]
    feedback: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None
    claimed_by: str | None
    created_by: str
    parent_task_id: str | None
    created_at: str
    updated_at: str
    started_at: str | None
    completed_at: str | None


def row_to_task(row) -> Task:
    d = dict(row)
    for k, default in (("inputs", {}), ("depends_on", []), ("acceptance", []), ("artifacts", []), ("history", []), ("feedback", [])):
        d[k] = loads(d[k], default)
    d["result"] = loads(d["result"], None)
    return Task(**d)


class TaskStore:
    def __init__(self, db: Database, events: EventBus):
        self.db = db
        self.events = events

    # ---------- Anlegen ----------
    def create(self, spec: TaskSpec, *, run_id: str | None = None) -> tuple[Task, bool]:
        """Legt eine Aufgabe an. Existiert der Key bereits, wird die bestehende zurückgegeben (kein Duplikat)."""
        existing = self.get_by_key(spec.key)
        if existing:
            return existing, False
        task_id = "T-" + uuid.uuid4().hex[:8]
        ts = now_iso()
        history = [{"ts": ts, "status": "pending", "note": f"angelegt von {spec.created_by}"}]
        with self.db.connect() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO tasks(id, key, agent, kind, title, goal, description, phase, inputs, depends_on,"
                " output_format, acceptance, priority, status, review_by, not_before_day, history, created_by,"
                " parent_task_id, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (task_id, spec.key, spec.agent, spec.kind, spec.title, spec.goal, spec.description, spec.phase,
                 dumps(spec.inputs), dumps(spec.depends_on), spec.output_format, dumps(spec.acceptance), spec.priority,
                 "pending", spec.review_by, spec.not_before_day, dumps(history), spec.created_by, spec.parent_task_id, ts, ts),
            )
            if cur.rowcount != 1:  # paralleles Anlegen desselben Keys
                return self.get_by_key(spec.key), False  # type: ignore[return-value]
        task = self.get(task_id)
        self.events.emit(
            "task.created", f"Neue Aufgabe: {spec.title}", agent=spec.created_by if spec.created_by != "system" else None,
            task_id=task_id, run_id=run_id, data={"key": spec.key, "owner": spec.agent, "phase": spec.phase},
        )
        return task, True  # type: ignore[return-value]

    # ---------- Lesen ----------
    def get(self, task_id: str) -> Task | None:
        row = self.db.query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
        return row_to_task(row) if row else None

    def get_by_key(self, key: str) -> Task | None:
        row = self.db.query_one("SELECT * FROM tasks WHERE key = ?", (key,))
        return row_to_task(row) if row else None

    def list(self, *, agent: str | None = None, status: str | None = None) -> list[Task]:
        sql, params = "SELECT * FROM tasks WHERE 1=1", []
        if agent:
            sql += " AND agent = ?"
            params.append(agent)
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY phase, priority DESC, created_at"
        return [row_to_task(r) for r in self.db.query(sql, params)]

    def by_keys(self) -> dict[str, Task]:
        return {t.key: t for t in self.list()}

    def dependencies_met(self, task: Task, by_key: dict[str, Task]) -> bool:
        return all(dep in by_key and by_key[dep].status == S.COMPLETED for dep in task.depends_on)

    def ready(self, *, current_day: int, paused_agents: set[str]) -> list[Task]:
        by_key = self.by_keys()
        ready = [
            t for t in by_key.values()
            if t.status == S.PENDING and t.agent not in paused_agents and t.not_before_day <= current_day
            and self.dependencies_met(t, by_key)
        ]
        return sorted(ready, key=lambda t: (t.phase, -t.priority, t.created_at))

    # ---------- Zustandswechsel ----------
    def transition(
        self,
        task_id: str,
        new: TaskStatus,
        *,
        note: str,
        expected: set[TaskStatus] | None = None,
        updates: dict[str, Any] | None = None,
        actor: str = "system",
    ) -> Task:
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not row:
                raise InvalidTransition(f"Aufgabe {task_id} existiert nicht")
            current = TaskStatus(row["status"])
            if expected and current not in expected:
                raise InvalidTransition(f"{task_id}: Status {current} statt {sorted(expected)}")
            if new not in ALLOWED_TRANSITIONS[current] and new != current:
                raise InvalidTransition(f"{task_id}: Übergang {current} → {new} nicht erlaubt")
            ts = now_iso()
            history = loads(row["history"], [])
            history.append({"ts": ts, "from": current.value, "status": new.value, "note": note, "actor": actor})
            fields: dict[str, Any] = {"status": new.value, "history": dumps(history), "updated_at": ts}
            if new == S.IN_PROGRESS:
                fields["started_at"] = ts
            if new == S.COMPLETED:
                fields["completed_at"] = ts
            if new in (S.PENDING, S.COMPLETED, S.FAILED, S.BLOCKED):
                fields["claimed_by"] = None
            for k, v in (updates or {}).items():
                fields[k] = dumps(v) if isinstance(v, (dict, list)) else v
            sets = ", ".join(f"{k} = ?" for k in fields)
            conn.execute(f"UPDATE tasks SET {sets} WHERE id = ?", (*fields.values(), task_id))
        return self.get(task_id)  # type: ignore[return-value]

    def claim(self, task_id: str, run_id: str) -> bool:
        """Atomare Übernahme: nur ein Lauf kann eine wartende Aufgabe starten (Schutz vor Doppelausführung)."""
        ts = now_iso()
        with self.db.transaction() as conn:
            row = conn.execute("SELECT status, history FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not row or row["status"] != S.PENDING:
                return False
            history = loads(row["history"], [])
            history.append({"ts": ts, "from": "pending", "status": "in_progress", "note": f"übernommen von Lauf {run_id}"})
            cur = conn.execute(
                "UPDATE tasks SET status='in_progress', claimed_by=?, started_at=?, updated_at=?, history=?,"
                " attempt_count = attempt_count + 1 WHERE id=? AND status='pending'",
                (run_id, ts, ts, dumps(history), task_id),
            )
            return cur.rowcount == 1

    def add_feedback(self, task_id: str, source: str, message: str, details: Any = None) -> None:
        with self.db.transaction() as conn:
            row = conn.execute("SELECT feedback FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None:
                return
            fb = loads(row["feedback"], [])
            fb.append({"ts": now_iso(), "from": source, "message": message, "details": details})
            conn.execute("UPDATE tasks SET feedback = ? WHERE id = ?", (dumps(fb[-6:]), task_id))

    def set_fields(self, task_id: str, **fields: Any) -> None:
        if not fields:
            return
        values = [dumps(v) if isinstance(v, (dict, list)) else v for v in fields.values()]
        sets = ", ".join(f"{k} = ?" for k in fields)
        self.db.execute(f"UPDATE tasks SET {sets}, updated_at = ? WHERE id = ?", (*values, now_iso(), task_id))

    def add_dependency(self, task_id: str, dep_key: str) -> None:
        task = self.get(task_id)
        if task and dep_key not in task.depends_on:
            self.set_fields(task_id, depends_on=task.depends_on + [dep_key])

    # ---------- Wiederanlauf & Blockaden ----------
    def recover_stale(self, active_run_ids: set[str], run_id: str | None = None) -> list[Task]:
        """Aufgaben, die von einem abgestürzten Lauf übernommen wurden, wieder einplanen."""
        recovered = []
        for t in self.list(status=S.IN_PROGRESS):
            if t.claimed_by not in active_run_ids:
                t2 = self.transition(t.id, S.PENDING, note=f"Wiederaufnahme nach Abbruch von Lauf {t.claimed_by}",
                                     expected={S.IN_PROGRESS}, actor="operations")
                self.events.emit(
                    "task.recovered", f"Aufgabe nach Neustart wieder eingeplant: {t.title}", agent="operations",
                    task_id=t.id, run_id=run_id, severity="warning", data={"previous_run": t.claimed_by, "automated": True},
                )
                recovered.append(t2)
        return recovered

    def propagate_blocks(self, run_id: str | None = None) -> list[Task]:
        """Aufgaben blockieren, deren Abhängigkeit endgültig fehlgeschlagen ist."""
        changed = []
        by_key = self.by_keys()
        for t in by_key.values():
            if t.status != S.PENDING:
                continue
            bad = [d for d in t.depends_on if d in by_key and by_key[d].status in (S.FAILED, S.BLOCKED)]
            if bad:
                t2 = self.transition(t.id, S.BLOCKED, note=f"blockiert durch {', '.join(bad)}", expected={S.PENDING},
                                     updates={"error": f"Abhängigkeit fehlgeschlagen: {', '.join(bad)}"})
                self.events.emit("task.blocked", f"Blockiert: {t.title} (wartet auf fehlgeschlagene Abhängigkeit)",
                                 agent=t.agent, task_id=t.id, run_id=run_id, severity="warning",
                                 data={"blocked_by": bad})
                changed.append(t2)
                by_key[t.key] = t2
        return changed

    def retry(self, task_id: str, actor: str) -> Task:
        """Manueller Neustart einer fehlgeschlagenen/blockierten Aufgabe (inkl. blockierter Nachfolger)."""
        task = self.get(task_id)
        if not task or task.status not in (S.FAILED, S.BLOCKED):
            raise InvalidTransition("Nur fehlgeschlagene oder blockierte Aufgaben können erneut versucht werden")
        t = self.transition(task_id, S.PENDING, note=f"erneuter Versuch angefordert von {actor}", actor=actor,
                            updates={"revision_count": 0, "attempt_count": 0, "error": None})
        for other in self.list(status=S.BLOCKED):
            if task.key in other.depends_on:
                self.transition(other.id, S.PENDING, note=f"Abhängigkeit {task.key} wird erneut versucht", actor=actor,
                                updates={"error": None})
        return t

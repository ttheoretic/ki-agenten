"""Freigabezentrum: strukturierte Anträge, serverseitige Validierung, idempotente Ausführung.

Garantien (im Programm, nicht im UI):
- Nur Aktionstypen der Klasse "approval" können beantragt werden; verbotene werden abgewiesen.
- Parameter sind nach Antragstellung unveränderlich (Hash). Die Genehmigung muss den Hash bestätigen,
  den der Mensch gesehen hat. Ändern sich Betrag, Empfänger oder Umfang, ist ein neuer Antrag nötig.
- Ausführung genau einmal: bedingtes UPDATE `execution_status='not_started' → 'running'`.
- Genehmigung ≠ Ausführung: der tatsächliche Ausführungsstatus wird separat gespeichert.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from .actions import EXECUTORS, PARAM_SCHEMAS, ExecutionContext, SpendParams
from .budget import BudgetGuard
from .config import Settings
from .control import ControlState
from .db import Database, dumps, loads, now_iso
from .events import EventBus
from .security import Redactor, SecurityPolicy

Decision = Literal["approve", "reject", "request_info", "defer"]
OPEN_STATES = ("pending", "info_requested", "deferred")


class ApprovalError(Exception):
    pass


class ApprovalRequest(BaseModel):
    id: str
    idem_key: str
    task_id: str | None
    agent: str
    action_type: str
    title: str
    description: str
    justification: str
    expected_benefit: str
    params: dict[str, Any]
    params_hash: str
    cost_eur: float
    recurring_cost_eur: float
    budget_impact: dict[str, Any]
    risks: list[str]
    alternatives: list[str]
    planned_at: str | None
    created_at: str
    expires_at: str | None
    status: str
    decided_at: str | None
    decided_by: str | None
    decision_note: str | None
    execution_status: str
    execution_result: dict[str, Any] | None
    executed_at: str | None


def row_to_approval(row) -> ApprovalRequest:
    d = dict(row)
    d["params"] = loads(d["params"], {})
    d["budget_impact"] = loads(d["budget_impact"], {})
    d["risks"] = loads(d["risks"], [])
    d["alternatives"] = loads(d["alternatives"], [])
    d["execution_result"] = loads(d["execution_result"], None)
    return ApprovalRequest(**d)


def params_hash(action_type: str, params: dict, cost_eur: float, recurring_cost_eur: float) -> str:
    canonical = json.dumps({"a": action_type, "p": params, "c": float(round(cost_eur, 4)), "r": float(round(recurring_cost_eur, 4))},
                           sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


class ApprovalService:
    def __init__(self, db: Database, events: EventBus, policy: SecurityPolicy, budget: BudgetGuard,
                 control: ControlState, settings: Settings, redactor: Redactor):
        self.db, self.events, self.policy, self.budget = db, events, policy, budget
        self.control, self.settings, self.redactor = control, settings, redactor

    # ---------- Antrag ----------
    def create(
        self,
        *,
        agent: str,
        task_id: str | None,
        action_type: str,
        title: str,
        description: str,
        justification: str,
        expected_benefit: str,
        params: dict[str, Any],
        cost_eur: float = 0.0,
        recurring_cost_eur: float = 0.0,
        risks: list[str] | None = None,
        alternatives: list[str] | None = None,
        planned_at: str | None = None,
        run_id: str | None = None,
    ) -> ApprovalRequest:
        cls = self.policy.classify(action_type)
        if cls == "forbidden":
            self.events.emit("security.violation", f"Verbotene Aktion abgewiesen: {action_type}", agent=agent,
                             task_id=task_id, run_id=run_id, severity="error", data={"action_type": action_type})
            raise ApprovalError(f"Aktion '{action_type}' ist verboten oder unbekannt")
        if cls == "auto":
            raise ApprovalError(f"Aktion '{action_type}' ist intern und braucht keinen Freigabeantrag")
        schema = PARAM_SCHEMAS.get(action_type)
        if schema is None:
            raise ApprovalError(f"Kein Parameterschema für '{action_type}'")
        try:
            validated = schema.model_validate(params).model_dump()
        except ValidationError as exc:
            raise ApprovalError(f"Ungültige Parameter für {action_type}: {exc.errors(include_url=False)}") from exc
        if cost_eur < 0 or recurring_cost_eur < 0:
            raise ApprovalError("Kosten dürfen nicht negativ sein")
        if action_type == "send_message":
            limit = self.settings.approvals.max_recipients_per_message
            if len(validated["recipients"]) > limit:
                self.events.emit("security.violation", f"Massenkommunikation abgewiesen ({len(validated['recipients'])} Empfänger)",
                                 agent=agent, task_id=task_id, run_id=run_id, severity="error")
                raise ApprovalError(f"Mehr als {limit} Empfänger gelten als Massenkommunikation und sind verboten")
        if schema is SpendParams:
            amount = validated["amount_eur"]
            if validated["recurring"] == "none" and abs(amount - cost_eur) > 0.005:
                raise ApprovalError("Antragsbetrag und Parameterbetrag stimmen nicht überein")
            if validated["recurring"] != "none" and abs(amount - recurring_cost_eur) > 0.005:
                raise ApprovalError("Wiederkehrender Betrag und Parameterbetrag stimmen nicht überein")
        validated = self.redactor.redact_obj(validated)
        p_hash = params_hash(action_type, validated, cost_eur, recurring_cost_eur)
        idem = hashlib.sha256(f"{task_id}|{action_type}|{p_hash}".encode()).hexdigest()
        existing = self.db.query_one("SELECT * FROM approvals WHERE idem_key = ?", (idem,))
        if existing:
            return row_to_approval(existing)
        summary = self.budget.summary()
        impact = {
            "one_time_eur": cost_eur,
            "recurring_eur": recurring_cost_eur,
            "total_remaining_before_eur": summary["total_remaining_eur"],
            "total_remaining_after_eur": round(summary["total_remaining_eur"] - cost_eur - recurring_cost_eur, 2),
            "fits_budget": cost_eur + recurring_cost_eur <= summary["total_remaining_eur"],
        }
        ap_id = "A-" + uuid.uuid4().hex[:8]
        created = now_iso()
        expires = (datetime.now(timezone.utc) + timedelta(hours=self.settings.approvals.default_expiry_hours)).isoformat(timespec="seconds")
        self.db.execute(
            "INSERT OR IGNORE INTO approvals(id, idem_key, task_id, agent, action_type, title, description, justification,"
            " expected_benefit, params, params_hash, cost_eur, recurring_cost_eur, budget_impact, risks, alternatives,"
            " planned_at, created_at, expires_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ap_id, idem, task_id, agent, action_type, self.redactor.redact(title), self.redactor.redact(description),
             self.redactor.redact(justification), self.redactor.redact(expected_benefit), dumps(validated), p_hash,
             cost_eur, recurring_cost_eur, dumps(impact), dumps(risks or []), dumps(alternatives or []), planned_at,
             created, expires),
        )
        ap = self.get(ap_id) or row_to_approval(self.db.query_one("SELECT * FROM approvals WHERE idem_key=?", (idem,)))
        self.events.emit(
            "approval.requested", f"Freigabe beantragt: {title} ({action_type}, {cost_eur:.2f} €)", agent=agent,
            task_id=task_id, run_id=run_id, approval_id=ap.id, severity="warning",
            data={"action_type": action_type, "cost_eur": cost_eur},
        )
        return ap

    # ---------- Lesen ----------
    def get(self, approval_id: str) -> ApprovalRequest | None:
        row = self.db.query_one("SELECT * FROM approvals WHERE id = ?", (approval_id,))
        return row_to_approval(row) if row else None

    def list(self, status: str | None = None) -> list[ApprovalRequest]:
        if status == "open":
            rows = self.db.query(f"SELECT * FROM approvals WHERE status IN ({','.join('?'*len(OPEN_STATES))}) ORDER BY created_at",
                                 OPEN_STATES)
        elif status:
            rows = self.db.query("SELECT * FROM approvals WHERE status = ? ORDER BY created_at DESC", (status,))
        else:
            rows = self.db.query("SELECT * FROM approvals ORDER BY created_at DESC")
        return [row_to_approval(r) for r in rows]

    def expire_old(self) -> int:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rows = self.db.query(
            f"SELECT id, agent, title FROM approvals WHERE status IN ({','.join('?'*len(OPEN_STATES))}) AND expires_at IS NOT NULL AND expires_at < ?",
            (*OPEN_STATES, now),
        )
        for r in rows:
            cur = self.db.execute("UPDATE approvals SET status='expired' WHERE id=? AND status IN ('pending','info_requested','deferred')", (r["id"],))
            if cur.rowcount:
                self.events.emit("approval.expired", f"Freigabeantrag abgelaufen: {r['title']}", agent=r["agent"],
                                 approval_id=r["id"], severity="warning")
        return len(rows)

    # ---------- Entscheidung ----------
    def decide(self, approval_id: str, decision: Decision, *, actor: str, confirmed_hash: str | None, note: str = "") -> ApprovalRequest:
        self.expire_old()
        ap = self.get(approval_id)
        if ap is None:
            raise ApprovalError("Antrag nicht gefunden")
        if ap.status not in OPEN_STATES:
            raise ApprovalError(f"Antrag ist bereits entschieden ({ap.status})")
        if decision not in ("approve", "reject", "request_info", "defer"):
            raise ApprovalError("Unbekannte Entscheidung")
        if decision == "approve":
            if not confirmed_hash or confirmed_hash != ap.params_hash:
                raise ApprovalError("Parameter-Hash stimmt nicht – der Antrag wurde geändert oder nicht vollständig angezeigt")
            if params_hash(ap.action_type, ap.params, ap.cost_eur, ap.recurring_cost_eur) != ap.params_hash:
                raise ApprovalError("Gespeicherte Parameter wurden manipuliert – Antrag ungültig")
            if self.policy.classify(ap.action_type) != "approval":
                raise ApprovalError("Aktion ist laut aktueller Sicherheitsrichtlinie nicht (mehr) genehmigungsfähig")
            remaining = self.budget.summary()["total_remaining_eur"]
            if ap.cost_eur + ap.recurring_cost_eur > remaining:
                raise ApprovalError(f"Kosten {ap.cost_eur + ap.recurring_cost_eur:.2f} € übersteigen das Restbudget {remaining:.2f} €")
        new_status = {"approve": "approved", "reject": "rejected", "request_info": "info_requested", "defer": "deferred"}[decision]
        placeholders = ",".join("?" * len(OPEN_STATES))
        cur = self.db.execute(
            f"UPDATE approvals SET status=?, decided_at=?, decided_by=?, decision_note=? WHERE id=? AND status IN ({placeholders})",
            (new_status, now_iso(), actor, self.redactor.redact(note), approval_id, *OPEN_STATES),
        )
        if cur.rowcount != 1:
            raise ApprovalError("Antrag wurde parallel entschieden")
        self.db.audit(actor, f"approval.{decision}", approval_id, {"note": note, "params_hash": ap.params_hash})
        labels = {"approved": "genehmigt", "rejected": "abgelehnt", "info_requested": "Rückfrage gestellt", "deferred": "zurückgestellt"}
        self.events.emit(
            "approval.decided", f"Freigabe {labels[new_status]}: {ap.title}", agent=ap.agent, task_id=ap.task_id,
            approval_id=ap.id, severity="success" if new_status == "approved" else "info",
            data={"decision": new_status, "actor": actor, "note": note},
        )
        if new_status == "info_requested" and note:
            # Rückfrage an den anfragenden Agenten weitergeben (wird bei der nächsten Aufgabe berücksichtigt)
            if ap.task_id:
                from .tasks import TaskStore  # lokale Abhängigkeit vermeiden
                TaskStore(self.db, self.events).add_feedback(ap.task_id, "owner", f"Rückfrage zu Antrag {ap.id}: {note}")
        return self.get(approval_id)  # type: ignore[return-value]

    # ---------- Ausführung ----------
    def execute(self, approval_id: str, *, actor: str = "system") -> ApprovalRequest:
        ap = self.get(approval_id)
        if ap is None:
            raise ApprovalError("Antrag nicht gefunden")
        if ap.status != "approved":
            raise ApprovalError("Nur genehmigte Anträge können ausgeführt werden")
        if ap.execution_status != "not_started":
            return ap  # idempotent: bereits gestartet/ausgeführt
        ok, reason = self.control.may_execute_external()
        if not ok:
            self.events.emit("approval.execution_blocked", f"Ausführung zurückgehalten: {reason}", agent=ap.agent,
                             approval_id=ap.id, severity="warning")
            return ap
        if ap.planned_at and ap.planned_at > now_iso():
            return ap
        cur = self.db.execute(
            "UPDATE approvals SET execution_status='running' WHERE id=? AND status='approved' AND execution_status='not_started'",
            (approval_id,),
        )
        if cur.rowcount != 1:
            return self.get(approval_id)  # type: ignore[return-value]
        self.events.emit("approval.executing", f"Ausführung läuft: {ap.title}", agent=ap.agent, approval_id=ap.id)
        try:
            if params_hash(ap.action_type, ap.params, ap.cost_eur, ap.recurring_cost_eur) != ap.params_hash:
                raise ApprovalError("Parameter weichen von der Genehmigung ab")
            params = PARAM_SCHEMAS[ap.action_type].model_validate(ap.params)
            ctx = ExecutionContext(self.settings.workspace_dir, self.settings.releases_dir, self.settings.outbox_dir, ap.id)
            result = EXECUTORS[ap.action_type](params, ctx)
            status, message, details = result.status, result.message, {**result.details, "external_effect": result.external_effect}
        except Exception as exc:  # Ausführungsfehler werden ehrlich gemeldet
            status, message, details = "failed", f"Ausführung fehlgeschlagen: {exc}", {}
        self.db.execute(
            "UPDATE approvals SET execution_status=?, execution_result=?, executed_at=? WHERE id=?",
            (status, dumps(self.redactor.redact_obj({"message": message, **details})), now_iso(), approval_id),
        )
        self.db.audit(actor, "approval.execute", approval_id, {"status": status})
        ev = {"succeeded": ("approval.executed", "success"), "failed": ("approval.failed", "error"),
              "manual_required": ("approval.manual_required", "warning")}[status]
        self.events.emit(ev[0], f"{ap.title}: {message}", agent=ap.agent, approval_id=ap.id, task_id=ap.task_id,
                         severity=ev[1], data={"execution_status": status})
        return self.get(approval_id)  # type: ignore[return-value]

    def confirm_manual(self, approval_id: str, *, actor: str, executed: bool, actual_cost_eur: float, note: str) -> ApprovalRequest:
        ap = self.get(approval_id)
        if ap is None or ap.execution_status != "manual_required":
            raise ApprovalError("Nur Anträge mit Status 'manuelle Ausführung erforderlich' können bestätigt werden")
        if actual_cost_eur < 0:
            raise ApprovalError("Kosten dürfen nicht negativ sein")
        if executed and actual_cost_eur > ap.cost_eur + ap.recurring_cost_eur + 0.005:
            raise ApprovalError("Tatsächliche Kosten übersteigen den genehmigten Betrag – neuer Antrag erforderlich")
        new = "succeeded" if executed else "failed"
        cur = self.db.execute(
            "UPDATE approvals SET execution_status=?, execution_result=?, executed_at=? WHERE id=? AND execution_status='manual_required'",
            (new, dumps({**(ap.execution_result or {}), "manual_confirmation": note, "confirmed_by": actor,
                         "actual_cost_eur": actual_cost_eur}), now_iso(), approval_id),
        )
        if cur.rowcount != 1:
            raise ApprovalError("Bereits bestätigt")
        if executed and actual_cost_eur > 0:
            self.budget.record_external(approval_id=ap.id, agent=ap.agent, amount_eur=actual_cost_eur, note=ap.title)
        self.db.audit(actor, "approval.confirm_manual", approval_id, {"executed": executed, "cost": actual_cost_eur})
        self.events.emit(
            "approval.executed" if executed else "approval.failed",
            f"{ap.title}: manuell {'ausgeführt' if executed else 'nicht ausgeführt'} (bestätigt durch {actor})",
            agent=ap.agent, approval_id=ap.id, severity="success" if executed else "warning",
            data={"actual_cost_eur": actual_cost_eur},
        )
        return self.get(approval_id)  # type: ignore[return-value]

    def execute_due(self) -> list[ApprovalRequest]:
        rows = self.db.query("SELECT id FROM approvals WHERE status='approved' AND execution_status='not_started'")
        return [self.execute(r["id"]) for r in rows]

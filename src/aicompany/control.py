"""Globale und agentenbezogene Steuerung (Pausieren, Fortsetzen, Stoppen).

Die Flags liegen in der Datenbank, damit der Server einen laufenden CLI-/Scheduler-Prozess
steuern kann. Der Orchestrator prüft sie vor jeder Aufgabenvergabe und während laufender Aufrufe.

- paused:          keine neuen Aufgaben, keine externen Aktionen; laufende Aufrufe dürfen fertig werden.
- stop_new_tasks:  keine neuen Aufgaben/Läufe; laufende Aufgaben werden geordnet abgeschlossen.
- shutdown:        wie stop_new_tasks, zusätzlich werden laufende Agentenaufrufe abgebrochen
                   (die Aufgaben gehen zurück auf "pending"); keine externen Aktionen.
"""
from __future__ import annotations

from .db import Database, now_iso
from .events import EventBus

FLAGS = ("paused", "stop_new_tasks", "shutdown")


class ControlState:
    def __init__(self, db: Database, events: EventBus):
        self.db = db
        self.events = events

    def flags(self) -> dict[str, bool]:
        rows = {r["key"]: r["value"] for r in self.db.query("SELECT key, value FROM control")}
        return {f: rows.get(f) == "1" for f in FLAGS}

    def _set(self, key: str, value: bool) -> None:
        self.db.execute(
            "INSERT INTO control(key, value, updated_at) VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,"
            " updated_at=excluded.updated_at", (key, "1" if value else "0", now_iso()),
        )

    def company_status(self) -> str:
        f = self.flags()
        if f["shutdown"]:
            return "stopped"
        if f["stop_new_tasks"]:
            return "draining"
        if f["paused"]:
            return "paused"
        return "active"

    def may_dispatch(self) -> tuple[bool, str]:
        f = self.flags()
        if f["shutdown"]:
            return False, "Unternehmen gestoppt"
        if f["stop_new_tasks"]:
            return False, "Neue Aufgaben gestoppt"
        if f["paused"]:
            return False, "Unternehmen pausiert"
        return True, ""

    def may_execute_external(self) -> tuple[bool, str]:
        return self.may_dispatch()

    def apply(self, action: str, actor: str) -> dict[str, bool]:
        if action == "pause":
            self._set("paused", True)
            msg = "Unternehmen pausiert – keine neuen Aufgaben und externen Aktionen"
        elif action == "resume":
            for f in FLAGS:
                self._set(f, False)
            msg = "Betrieb fortgesetzt"
        elif action == "stop_new":
            self._set("stop_new_tasks", True)
            msg = "Neue Aufgaben gestoppt – laufende Aufgaben werden geordnet abgeschlossen"
        elif action == "stop":
            self._set("stop_new_tasks", True)
            self._set("shutdown", True)
            msg = "Stopp angefordert – laufende Aufrufe werden kontrolliert abgebrochen, keine externen Aktionen"
        else:
            raise ValueError(f"Unbekannte Steuerungsaktion: {action}")
        self.db.audit(actor, f"control.{action}", "company")
        self.events.emit(f"control.{action}", msg, agent=None, severity="warning" if action != "resume" else "info",
                         data={"actor": actor, "flags": self.flags()})
        return self.flags()

    # ---------- einzelne Agenten ----------
    def paused_agents(self) -> set[str]:
        return {r["agent"] for r in self.db.query("SELECT agent FROM agent_control WHERE paused = 1")}

    def set_agent_paused(self, agent: str, paused: bool, actor: str) -> None:
        self.db.execute(
            "INSERT INTO agent_control(agent, paused, updated_at) VALUES (?,?,?) ON CONFLICT(agent) DO UPDATE SET"
            " paused=excluded.paused, updated_at=excluded.updated_at", (agent, int(paused), now_iso()),
        )
        self.db.audit(actor, "agent.pause" if paused else "agent.resume", agent)
        self.events.emit(
            "control.agent_paused" if paused else "control.agent_resumed",
            f"Agent {agent} {'pausiert' if paused else 'wieder aktiviert'}", agent=agent,
            severity="warning" if paused else "info", data={"actor": actor},
        )

"""Begrenzter Scheduler für wiederkehrende Geschäftsläufe.

Kein endloser Prozess: Der Scheduler endet nach `max_total_runs`, am Ende des Experiments,
bei `stop_new`/`stop` oder bei ausgeschöpftem Budget. Pro Kalendertag gilt `max_runs_per_day`; nach `max_idle_cycles` Wartezyklen ohne Lauf endet er ebenfalls.
Alternativ kann `aicompany run` per cron/systemd-Timer gestartet werden (siehe README).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from .company import Company
from .orchestrator import Orchestrator, RunActive


async def run_scheduler(company: Company, *, interval_minutes: int, max_total_runs: int, max_runs_per_day: int,
                        max_idle_cycles: int = 48, sleep=asyncio.sleep, log=print) -> int:
    runs = idle = 0
    while runs < max_total_runs:
        if idle >= max_idle_cycles:
            log(f"Scheduler beendet: {max_idle_cycles} Wartezyklen ohne Lauf")
            break
        flags = company.control.flags()
        if flags["shutdown"] or flags["stop_new_tasks"]:
            log("Scheduler beendet: Stopp angefordert")
            break
        if company.db.get_meta("experiment_status") == "finished":
            log("Scheduler beendet: Experiment abgeschlossen")
            break
        if company.budget.exhausted():
            log("Scheduler beendet: Budget ausgeschöpft")
            break
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        today_runs = company.db.query_one("SELECT COUNT(*) AS n FROM runs WHERE substr(started_at,1,10)=? AND status!='skipped'", (today,))["n"]
        if flags["paused"]:
            idle += 1
            log("Unternehmen pausiert – warte")
        elif today_runs >= max_runs_per_day:
            idle += 1
            log(f"Tageslimit von {max_runs_per_day} Läufen erreicht – warte")
        else:
            idle = 0
            try:
                summary = await Orchestrator(company).run_once("scheduler")
                runs += 1
                log(f"Lauf {summary.run_id}: {summary.status} – {summary.stop_reason} ({summary.agent_calls} Aufrufe, {summary.cost_eur:.4f} €)")
            except RunActive as exc:
                log(f"Übersprungen: {exc}")
        if runs >= max_total_runs:
            break
        await sleep(interval_minutes * 60)
    return runs

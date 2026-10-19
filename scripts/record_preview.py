"""Zeichnet einen echten Dry-Run für die Online-Vorschau des Control-Centers auf.

Ablauf: Gründung → Ideenauswahl → MVP → Marktvorbereitung → Eigentümer genehmigt die Website und lehnt
Werbung ab → DEMO-Kennzahlen (viel Reichweite, keine Käufe) → CEO entscheidet „Kurswechsel“ → neuer Zyklus
mit der nächstbesten Idee. Alle Ereignisse, Zustände und Dateien stammen aus dem echten Backend; nur die
Agentenantworten sind simuliert und die Kennzahlen sind ausdrücklich als DEMO-Werte markiert.

    python scripts/record_preview.py  →  frontend/preview/replay.json
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aicompany.company import Company  # noqa: E402
from aicompany.config import load_settings  # noqa: E402
from aicompany.db import now_iso  # noqa: E402
from aicompany.llm.mock import MockBackend  # noqa: E402
from aicompany.orchestrator import Orchestrator  # noqa: E402
from aicompany.state import agent_detail, company_snapshot  # noqa: E402

DATA = ROOT / "data" / "preview"
OUT = ROOT / "frontend" / "preview" / "replay.json"
STATIC_AGENT_FIELDS = ("mission", "responsibilities", "rules", "tools", "write_dirs", "task_kinds", "limits")


def owner_metric(c: Company, name: str, value: float) -> None:
    c.db.execute("INSERT INTO metrics(ts, name, value, unit, source, note) VALUES (?,?,?,?,?,?)",
                 (now_iso(), name, value, "", "manual", "DEMO-Wert für die Vorschau"))
    c.events.emit("metric.recorded", f"Kennzahl erfasst (DEMO-Wert): {name} = {value:g}", agent="analytics",
                  data={"name": name, "value": value, "source": "manual", "demo": True})


def script(c: Company, done: threading.Event) -> None:
    def run():
        s = asyncio.run(Orchestrator(c).run_once("vorschau"))
        print(f"  Lauf {s.run_id}: {s.stop_reason} ({s.agent_calls} Aufrufe) – Zyklus {c.clock.cycle()}")
        time.sleep(2.5)

    try:
        time.sleep(2)
        decided = metrics = False
        for _ in range(14):
            run()
            open_aps = c.approvals.list("open")
            if not decided and any(a.action_type == "publish_website" for a in open_aps):
                time.sleep(1.5)
                for a in open_aps:
                    if a.action_type == "publish_website":
                        c.approvals.decide(a.id, "approve", actor="Eigentümer (Vorschau)", confirmed_hash=a.params_hash,
                                           note="Impressum ausgefüllt – veröffentlichen")
                        c.approvals.execute(a.id, actor="Eigentümer (Vorschau)")
                        time.sleep(1.5)
                decided = True
            if decided and not metrics and c.clock.day() >= 6:
                for name, value in (("visitors", 180), ("inquiries", 1), ("visitors", 240), ("sales", 0)):
                    owner_metric(c, name, value)
                    time.sleep(1.0)
                metrics = True
            for a in c.approvals.list("open"):
                if a.action_type == "paid_ads":
                    time.sleep(1.0)
                    c.approvals.decide(a.id, "reject", actor="Eigentümer (Vorschau)", confirmed_hash=None,
                                       note="Erst organisch testen")
            if c.clock.cycle() >= 2 and c.db.get_meta("selected_idea") and \
                    (t := c.tasks.get_by_key("c2.p2.qa.product_test")) and t.status == "completed":
                break
        time.sleep(3)
    finally:
        done.set()


def main() -> None:
    if DATA.exists():
        shutil.rmtree(DATA)
    settings = load_settings(mode="dry_run", data_dir=DATA, overrides={"orchestrator": {"retry_backoff_seconds": 0.0}})
    c = Company(settings, backend=MockBackend(delay_seconds=0.7))
    start = time.time()
    start_iso = datetime.fromtimestamp(start).astimezone().isoformat()
    done = threading.Event()
    worker = threading.Thread(target=script, args=(c, done), daemon=True)
    worker.start()
    frames, prev = [], {}
    while True:
        snap = company_snapshot(c)
        snap.pop("selftest", None)
        snap["server"] = {"run_thread_busy": False, "last_run_error": None}
        patch = {k: v for k, v in snap.items() if prev.get(k) != v}
        if patch:
            frames.append({"t": round(time.time() - start, 2), "patch": patch})
            prev = json.loads(json.dumps(snap))
        if done.is_set():
            break
        time.sleep(0.5)
    events = []
    for e in c.events.list(limit=2000):
        d = e.model_dump()
        d["t"] = round(datetime.fromisoformat(e.ts).timestamp() - start, 2)
        events.append(d)
    agents = {}
    for a in snap["agents"]:
        det = agent_detail(c, a["id"])
        agents[a["id"]] = {k: det[k] for k in STATIC_AGENT_FIELDS}
    tasks = {t.id: t.model_dump(mode="json") for t in c.tasks.list()}
    files = []
    for r in c.db.query("SELECT * FROM artifacts ORDER BY created_at"):
        try:
            content = c.sandbox.read_text(r["path"], max_bytes=40_000)
        except Exception:
            content = ""
        files.append({**dict(r), "content": content})
    data = {"meta": {"recorded_at": start_iso, "start_ms": int(start * 1000), "duration": frames[-1]["t"],
                     "note": "Aufzeichnung eines Dry-Runs: simulierte Agentenantworten, Eigentümer-Entscheidungen und Kennzahlen sind DEMO-Werte."},
            "frames": frames, "events": events, "agents": agents, "tasks": tasks, "files": files}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    print(f"{len(frames)} Frames, {len(events)} Ereignisse, {len(files)} Dateien, {frames[-1]['t']:.0f} s → {OUT} "
          f"({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()

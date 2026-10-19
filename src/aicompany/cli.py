"""Kommandozeile: aicompany <befehl>

  init        Datenverzeichnis, Datenbank und Owner-Token anlegen
  selftest    Automatisierte Tests ausführen (Voraussetzung für den Live-Modus)
  preflight   Prüfen, ob der Live-Modus startbereit ist
  run         Einen Geschäftslauf ausführen
  demo        Vollständigen Dry-Run des 30-Tage-Zyklus in frischem Verzeichnis ausführen
  scheduler   Begrenzte, wiederkehrende Läufe
  serve       Control-Center (Web-UI + API) starten
  status      Kurzstatus ausgeben
  report      Managementbericht erzeugen
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys

from .config import PROJECT_ROOT, load_settings


def _company(args, **overrides):
    from .company import Company

    settings = load_settings(mode=getattr(args, "mode", None), data_dir=getattr(args, "data_dir", None), overrides=overrides or None)
    return Company(settings)


def cmd_init(args) -> int:
    c = _company(args)
    print(f"Initialisiert: {c.settings.data_dir} (Modus {c.settings.mode})")
    print(f"Owner-Token gespeichert in {c.settings.token_path}")
    return 0


def cmd_selftest(args) -> int:
    from .preflight import run_selftest

    passed, output = run_selftest()
    print(output)
    print("SELBSTTEST BESTANDEN" if passed else "SELBSTTEST FEHLGESCHLAGEN")
    return 0 if passed else 1


def cmd_preflight(args) -> int:
    from .preflight import live_readiness

    settings = load_settings(mode="live")
    problems = live_readiness(settings)
    if problems:
        print("Live-Modus NICHT startbereit:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("Live-Modus startbereit.")
    return 0


def _print_summary(s) -> None:
    print(f"{s.run_id}: {s.status} | Tag {s.experiment_day} | {s.agent_calls} Aufrufe | {s.cost_eur:.4f} € | {s.stop_reason}")
    if s.completed:
        print("  abgeschlossen: " + ", ".join(s.completed))
    if s.report_path:
        print(f"  Bericht: workspace/{s.report_path}")


def cmd_run(args) -> int:
    from .orchestrator import Orchestrator, RunActive
    from .preflight import PreflightError

    try:
        c = _company(args)
        summary = asyncio.run(Orchestrator(c).run_once("cli"))
    except (RunActive, PreflightError) as exc:
        print(exc, file=sys.stderr)
        return 2
    _print_summary(summary)
    return 0


def cmd_demo(args) -> int:
    from .company import Company
    from .orchestrator import Orchestrator

    data_dir = PROJECT_ROOT / "data" / "demo"
    if data_dir.exists() and not args.keep:
        shutil.rmtree(data_dir)
    settings = load_settings(mode="dry_run", data_dir=data_dir,
                             overrides={"orchestrator": {"retry_backoff_seconds": 0.0}})
    c = Company(settings)
    print(f"DRY-RUN in {data_dir} – alle Agentenantworten sind simuliert, es entstehen keine API-Kosten.")
    for _ in range(args.max_runs):
        s = asyncio.run(Orchestrator(c).run_once("demo"))
        _print_summary(s)
        if c.db.get_meta("experiment_status") == "finished" or s.status in ("skipped", "failed", "budget_exhausted") \
                or c.clock.cycle() > args.cycles:
            break
    print(f"\nAktueller Zyklus: {c.clock.cycle()} ({c.clock.cycle_type()})")
    print(f"Offene Freigaben: {len(c.approvals.list('open'))}. Control-Center: aicompany serve --data-dir {data_dir}")
    return 0


def cmd_scheduler(args) -> int:
    from .scheduler import run_scheduler

    c = _company(args)
    cfg = c.settings.scheduler
    n = asyncio.run(run_scheduler(c, interval_minutes=args.interval or cfg.interval_minutes, max_total_runs=args.max_runs,
                                  max_runs_per_day=cfg.max_runs_per_day))
    print(f"Scheduler beendet nach {n} Läufen")
    return 0


def cmd_serve(args) -> int:
    import uvicorn

    from .api.app import create_app

    c = _company(args)
    host = args.host or c.settings.server.host
    port = args.port or c.settings.server.port
    if host not in ("127.0.0.1", "localhost"):
        print("WARNUNG: Server ist nicht nur lokal erreichbar. Owner-Token geheim halten und TLS vorschalten.", file=sys.stderr)
    print(f"Control-Center: http://{host}:{port}/#token={c.owner_token}")
    print(f"Modus: {c.mode_label()} – Daten: {c.settings.data_dir}")
    uvicorn.run(create_app(c), host=host, port=port, log_level="warning")
    return 0


def cmd_status(args) -> int:
    from .state import company_snapshot

    s = company_snapshot(_company(args))
    out = {
        "mode": s["mode_label"], "status": s["company"]["status"], "day": s["experiment"]["day"],
        "phase": s["experiment"]["work_phase"]["name"], "selected_idea": (s["selected_idea"] or {}).get("name"),
        "progress": s["progress"], "budget": {k: s["budget"][k] for k in ("api_spent_eur", "api_limit_eur", "total_remaining_eur")},
        "open_approvals": [a["id"] for a in s["approvals"] if a["status"] in ("pending", "info_requested", "deferred")],
        "blockers": s["blockers"], "agents": {a["id"]: a["status_label"] for a in s["agents"]},
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_report(args) -> int:
    from .reports import write_report

    c = _company(args)
    path = write_report(c, title="Statusbericht")
    print(c.sandbox.read_text(path))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="aicompany", description="Autonomes KI-Unternehmen")
    p.add_argument("--mode", choices=["dry_run", "live"], default=None, help="überschreibt AICO_MODE")
    p.add_argument("--data-dir", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init").set_defaults(fn=cmd_init)
    sub.add_parser("selftest").set_defaults(fn=cmd_selftest)
    sub.add_parser("preflight").set_defaults(fn=cmd_preflight)
    sub.add_parser("run").set_defaults(fn=cmd_run)
    d = sub.add_parser("demo")
    d.add_argument("--max-runs", type=int, default=12)
    d.add_argument("--cycles", type=int, default=1, help="so viele Zyklen durchlaufen (danach Stopp der Demo)")
    d.add_argument("--keep", action="store_true", help="vorhandene Demo-Daten nicht löschen")
    d.set_defaults(fn=cmd_demo)
    sc = sub.add_parser("scheduler")
    sc.add_argument("--interval", type=int, default=None, help="Minuten zwischen Läufen")
    sc.add_argument("--max-runs", type=int, default=8, help="maximale Anzahl Läufe, danach Ende")
    sc.set_defaults(fn=cmd_scheduler)
    sv = sub.add_parser("serve")
    sv.add_argument("--host", default=None)
    sv.add_argument("--port", type=int, default=None)
    sv.set_defaults(fn=cmd_serve)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("report").set_defaults(fn=cmd_report)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())

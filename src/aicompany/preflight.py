"""Startvoraussetzungen für den Live-Modus.

Der Live-Modus startet nur, wenn
1. die automatisierten Tests für exakt diesen Codestand bestanden wurden (`aicompany selftest`),
2. ein OPENAI_API_KEY vorhanden ist,
3. für alle konfigurierten Modelle Preise hinterlegt sind (sonst keine verlässliche Kostenkontrolle).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import PROJECT_ROOT, Settings

MARKER = PROJECT_ROOT / "data" / "selftest.json"


class PreflightError(Exception):
    pass


def code_hash() -> str:
    h = hashlib.sha256()
    files = sorted((PROJECT_ROOT / "src" / "aicompany").rglob("*.py")) + [PROJECT_ROOT / "config" / "security.toml"]
    for f in files:
        h.update(str(f.relative_to(PROJECT_ROOT)).encode())
        h.update(f.read_bytes())
    return h.hexdigest()[:20]


def run_selftest(extra_args: list[str] | None = None) -> tuple[bool, str]:
    env = {**os.environ, "AICO_MODE": "dry_run"}
    env.pop("OPENAI_API_KEY", None)  # Tests dürfen niemals echte API-Aufrufe machen
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", str(PROJECT_ROOT / "tests"), *(extra_args or [])],
                          cwd=PROJECT_ROOT, env=env, capture_output=True, text=True)
    output = (proc.stdout + proc.stderr)[-4000:]
    passed = proc.returncode == 0
    MARKER.parent.mkdir(parents=True, exist_ok=True)
    MARKER.write_text(json.dumps({"passed": passed, "code_hash": code_hash(), "ts": datetime.now(timezone.utc).isoformat(),
                                  "summary": output.strip().splitlines()[-1] if output.strip() else ""}, indent=2))
    return passed, output


def selftest_status() -> dict:
    if not MARKER.exists():
        return {"passed": False, "reason": "Selbsttest wurde noch nicht ausgeführt"}
    data = json.loads(MARKER.read_text())
    if data.get("code_hash") != code_hash():
        return {**data, "passed": False, "reason": "Code wurde seit dem letzten Selbsttest geändert"}
    if not data.get("passed"):
        return {**data, "reason": "Letzter Selbsttest fehlgeschlagen"}
    return {**data, "reason": "ok"}


def live_readiness(settings: Settings) -> list[str]:
    problems = []
    st = selftest_status()
    if not st["passed"]:
        problems.append(f"Tests: {st['reason']} – bitte `aicompany selftest` ausführen")
    if not os.environ.get("OPENAI_API_KEY"):
        problems.append("OPENAI_API_KEY ist nicht gesetzt (.env)")
    models = {settings.models.default, settings.models.escalation} | {a.model for a in settings.agents.values() if a.model}
    unpriced = sorted(m for m in models if m not in settings.pricing)
    if unpriced:
        problems.append(f"Keine Preise konfiguriert für: {', '.join(unpriced)}")
    return problems


def assert_live_ready(settings: Settings) -> None:
    problems = live_readiness(settings)
    if problems:
        raise PreflightError("Live-Modus gesperrt:\n- " + "\n- ".join(problems))

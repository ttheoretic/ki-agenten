"""Werkbank des Software-Teams: Projektdateien bearbeiten und Tests isoliert ausführen.

Der Builder arbeitet wie ein Entwickler – Dateien anlegen, lesen, ändern, Tests laufen lassen,
Fehler beheben – aber ausschließlich über diese Werkbank:

- Dateien nur im eigenen Projektordner (Sandbox), nur erlaubte Dateitypen und Größen.
- Jede Python-Datei wird vor dem Speichern statisch geprüft (`checks.scan_python`): nur Standardbibliothek
  plus freigegebene Pakete, keine Prozess-, Netzwerk- oder Dateisystem-Eingriffe.
- Tests laufen in einer Kopie des Projekts:
  * ``docker``: Container ohne Netzwerk, schreibgeschützt, CPU-/Speicherlimit (Image ``aicompany-sandbox``)
  * ``subprocess``: eigener Prozess mit leerer Umgebung (keine Schlüssel), Zeit-, CPU-, Speicher- und Dateigrößenlimits
  * ``off``: keine Ausführung (QA prüft dann nur statisch)
"""
from __future__ import annotations

import functools
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from .checks import scan_python
from .security import PermissionDenied, Redactor, Sandbox

CODE_EXTENSIONS = (".py", ".html", ".css", ".js", ".md", ".txt", ".json", ".svg", ".toml", ".cfg", ".ini", ".yml", ".yaml", ".sql")
CODE_FILENAMES = ("Dockerfile", ".dockerignore", "requirements.txt", "Procfile")
ALLOWED_REQUIREMENTS = {"fastapi", "uvicorn", "pydantic", "pytest", "httpx", "starlette"}
SANDBOX_IMAGE = "aicompany-sandbox"


@dataclass
class TestRun:
    executed: bool
    passed: bool
    mode: str
    summary: str
    output: str
    problems: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"executed": self.executed, "passed": self.passed, "mode": self.mode, "summary": self.summary,
                "output": self.output[-3000:], "problems": self.problems[:20]}


@functools.lru_cache(maxsize=1)
def docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        r = subprocess.run(["docker", "image", "inspect", SANDBOX_IMAGE], capture_output=True, timeout=5)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def resolve_mode(mode: str) -> str:
    if mode == "auto":
        return "docker" if docker_available() else "subprocess"
    return mode


def _limits():  # pragma: no cover - läuft im Kindprozess
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
        resource.setrlimit(resource.RLIMIT_AS, (1_500_000_000, 1_500_000_000))
        resource.setrlimit(resource.RLIMIT_FSIZE, (50_000_000, 50_000_000))
        os.setsid()
    except Exception:
        pass


class Workbench:
    def __init__(self, sandbox: Sandbox, agent_id: str, root: str, redactor: Redactor, *, mode: str = "auto",
                 timeout: int = 90, max_files: int = 60, max_file_bytes: int = 200_000, on_event=None):
        self.sandbox, self.agent_id, self.root, self.redactor = sandbox, agent_id, root.strip("/"), redactor
        self.mode = resolve_mode(mode)
        self.timeout, self.max_files, self.max_file_bytes = timeout, max_files, max_file_bytes
        self.on_event = on_event or (lambda kind, msg, data: None)
        self.written: list[str] = []
        self.test_runs: list[TestRun] = []
        self.dirty = True  # seit dem letzten Testlauf geändert?

    # ---------- Pfade ----------
    def _rel(self, path: str) -> str:
        p = PurePosixPath(path.replace("\\", "/"))
        if p.is_absolute() or ".." in p.parts or not path.strip():
            raise PermissionDenied(f"Ungültiger Pfad: {path}")
        if p.name not in CODE_FILENAMES and p.suffix.lower() not in CODE_EXTENSIONS:
            raise PermissionDenied(f"Dateityp nicht erlaubt: {path}")
        return f"{self.root}/{p}"

    @property
    def dir(self) -> Path:
        return self.sandbox.resolve(self.root)

    # ---------- Werkzeuge ----------
    def list_files(self) -> list[str]:
        if not self.dir.exists():
            return []
        return sorted(str(p.relative_to(self.dir)) for p in self.dir.rglob("*") if p.is_file() and "__pycache__" not in p.parts)

    def read_file(self, path: str) -> str:
        return self.sandbox.read_text(self._rel(path), max_bytes=self.max_file_bytes)

    def write_file(self, path: str, content: str) -> str:
        rel = self._rel(path)
        if path not in self.list_files() and len(self.list_files()) >= self.max_files:
            raise PermissionDenied(f"Zu viele Dateien im Projekt (max. {self.max_files})")
        if path.endswith(".py"):
            problems = scan_python(content, path)
            if problems:
                raise PermissionDenied("Code abgewiesen: " + "; ".join(problems[:5]))
        if PurePosixPath(path).name == "requirements.txt":
            bad = [ln for ln in content.splitlines() if ln.strip() and not ln.startswith("#")
                   and ln.split("==")[0].split(">=")[0].split("[")[0].strip().lower() not in ALLOWED_REQUIREMENTS]
            if bad:
                raise PermissionDenied(f"Nicht freigegebene Abhängigkeiten: {bad}")
        self.sandbox.write_text(self.agent_id, rel, content, self.redactor)
        if path not in self.written:
            self.written.append(path)
        self.dirty = True
        self.on_event("code.file_written", f"Datei geschrieben: {self.root}/{path}", {"path": f"{self.root}/{path}", "bytes": len(content)})
        return f"OK: {path} gespeichert ({len(content)} Zeichen)"

    def delete_file(self, path: str) -> str:
        full = self.sandbox.check_write(self.agent_id, self._rel(path))
        if full.is_file():
            full.unlink()
            self.dirty = True
            return f"OK: {path} gelöscht"
        return f"{path} existiert nicht"

    def scan_project(self) -> list[str]:
        problems = []
        for f in self.list_files():
            if f.endswith(".py"):
                problems += scan_python(self.read_file(f), f)
        return problems

    def run_tests(self) -> TestRun:
        problems = self.scan_project()
        if problems:
            run = TestRun(False, False, self.mode, "Ausführung verweigert: Codeprüfung fehlgeschlagen", "", problems)
        elif self.mode == "off":
            run = TestRun(False, False, "off", "Testausführung ist deaktiviert (builder.execution = off)", "")
        elif not any(f.startswith("tests/") and f.endswith(".py") for f in self.list_files()):
            run = TestRun(False, False, self.mode, "Keine Tests vorhanden (tests/test_*.py)", "")
        else:
            run = self._execute()
        self.test_runs.append(run)
        self.dirty = False
        self.on_event("code.tests_run", f"Tests {'bestanden' if run.passed else 'nicht bestanden'}: {run.summary}",
                      {"passed": run.passed, "mode": run.mode, "summary": run.summary})
        return run

    def _execute(self) -> TestRun:
        with tempfile.TemporaryDirectory(prefix="aico-test-") as tmp:
            work = Path(tmp) / "project"
            shutil.copytree(self.dir, work, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            if self.mode == "docker":
                cmd = ["docker", "run", "--rm", "--network", "none", "--memory", "768m", "--cpus", "1", "--pids-limit", "128",
                       "--read-only", "--tmpfs", "/tmp:rw,size=64m", "-v", f"{work}:/app:rw", "-w", "/app", "--user", "65534:65534",
                       "-e", "HOME=/tmp", SANDBOX_IMAGE, "python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
                env = {"PATH": os.environ.get("PATH", "")}
                preexec = None
            else:
                cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--rootdir", str(work), str(work)]
                env = {"PATH": "/usr/bin:/bin", "HOME": tmp, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(work),
                       "LANG": "C.UTF-8", "NO_PROXY": "*"}
                preexec = _limits if os.name == "posix" else None
            try:
                proc = subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True, timeout=self.timeout,
                                      preexec_fn=preexec)
                out = self.redactor.redact((proc.stdout + proc.stderr)[-6000:])
                lines = [ln for ln in out.strip().splitlines() if ln.strip()]
                summary = lines[-1] if lines else f"Exitcode {proc.returncode}"
                return TestRun(True, proc.returncode == 0, self.mode, summary, out)
            except subprocess.TimeoutExpired:
                return TestRun(True, False, self.mode, f"Zeitüberschreitung nach {self.timeout}s", "")
            except OSError as exc:
                return TestRun(False, False, self.mode, f"Ausführung nicht möglich: {exc}", "")

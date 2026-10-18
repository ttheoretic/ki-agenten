"""Verdrahtung aller Bausteine zu einem Unternehmen (eine Datenbank, ein Workspace, ein Backend)."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

from .approvals import ApprovalService
from .budget import BudgetGuard
from .config import Settings
from .control import ControlState
from .db import Database
from .events import EventBus
from .llm.base import LLMBackend, LLMFatalError
from .security import Redactor, Sandbox, SecurityPolicy
from .tasks import TaskStore
from .workflow import ExperimentClock


class Company:
    def __init__(self, settings: Settings, backend: LLMBackend | None = None):
        self.settings = settings
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.policy = SecurityPolicy.load(settings.security_path)
        self.redactor = Redactor()
        self.db = Database(settings.db_path)
        self.events = EventBus(self.db, self.redactor)
        self.budget = BudgetGuard(self.db, settings, self.events)
        self.control = ControlState(self.db, self.events)
        self.tasks = TaskStore(self.db, self.events)
        self.sandbox = Sandbox(settings.workspace_dir, self.policy)
        self.approvals = ApprovalService(self.db, self.events, self.policy, self.budget, self.control, settings, self.redactor)
        clock_mode = settings.experiment.clock
        self.clock = ExperimentClock(self.db, mode=clock_mode, days=settings.experiment.days,
                                     days_per_run=settings.experiment.days_per_run)
        self._backend = backend
        self.owner_token = self._load_token()
        self.redactor.add(self.owner_token)
        self._check_policy_fingerprint()
        if not self.db.get_meta("mode"):
            self.db.set_meta("mode", settings.mode)

    # ---------- Owner-Token ----------
    def _load_token(self) -> str:
        env = os.environ.get("AICO_OWNER_TOKEN")
        if env:
            return env
        path: Path = self.settings.token_path
        if path.exists():
            return path.read_text().strip()
        token = secrets.token_urlsafe(24)
        path.write_text(token)
        try:
            path.chmod(0o600)
        except OSError:
            pass
        return token

    def _check_policy_fingerprint(self) -> None:
        old = self.db.get_meta("policy_fingerprint")
        if old != self.policy.fingerprint:
            self.db.set_meta("policy_fingerprint", self.policy.fingerprint)
            if old:
                self.events.emit("security.policy_changed", "Sicherheitsrichtlinie wurde außerhalb des Systems geändert",
                                 severity="warning", data={"old": old, "new": self.policy.fingerprint})

    # ---------- Backend ----------
    @property
    def backend(self) -> LLMBackend:
        if self._backend is None:
            self._backend = make_backend(self.settings)
        return self._backend

    def mode_label(self) -> str:
        return "DRY-RUN (simulierte Agentenantworten)" if self.settings.mode == "dry_run" else "LIVE"


def make_backend(settings: Settings) -> LLMBackend:
    if settings.mode == "dry_run":
        from .llm.mock import MockBackend
        return MockBackend()
    from .preflight import assert_live_ready
    assert_live_ready(settings)
    from .llm.openai_backend import OpenAIAgentsBackend
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise LLMFatalError("OPENAI_API_KEY fehlt – Live-Modus nicht möglich")
    return OpenAIAgentsBackend(api_key=key, disable_tracing=settings.models.disable_tracing,
                               timeout_seconds=settings.orchestrator.call_timeout_seconds)

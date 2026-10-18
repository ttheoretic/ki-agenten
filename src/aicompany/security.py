"""Sicherheitsmodell: Berechtigungen, Aktionsklassen, Pfad-Sandbox und Geheimnisschutz.

Alle Regeln werden im Programm durchgesetzt – die Agentenprompts beschreiben sie nur zusätzlich.
"""
from __future__ import annotations

import hashlib
import os
import re
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

ActionClass = Literal["auto", "approval", "forbidden"]


class PermissionDenied(Exception):
    """Ein Agent versucht etwas, das die Richtlinie nicht erlaubt."""


class AgentPermissions(BaseModel):
    model_config = ConfigDict(frozen=True)
    tools: tuple[str, ...] = ()
    write_dirs: tuple[str, ...] = ()


class Limits(BaseModel):
    model_config = ConfigDict(frozen=True)
    max_file_bytes: int = 200_000
    max_files_per_build: int = 20
    allowed_build_extensions: tuple[str, ...] = (".html", ".css", ".js", ".md", ".txt", ".json", ".svg")
    max_file_view_bytes: int = 300_000


class SecurityPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)
    auto_allowed: tuple[str, ...]
    approval_required: tuple[str, ...]
    forbidden: tuple[str, ...]
    agents: dict[str, AgentPermissions]
    limits: Limits = Limits()
    fingerprint: str = ""

    @classmethod
    def load(cls, path: Path) -> "SecurityPolicy":
        data = path.read_bytes()
        raw = tomllib.loads(data.decode("utf-8"))
        overlap = set(raw["approval_required"]) & set(raw["forbidden"])
        if overlap:
            raise ValueError(f"Aktionen gleichzeitig freigabepflichtig und verboten: {overlap}")
        return cls(**raw, fingerprint=hashlib.sha256(data).hexdigest()[:16])

    def classify(self, action_type: str) -> ActionClass:
        """Unbekannte Aktionen gelten als verboten (Default-Deny)."""
        if action_type in self.forbidden:
            return "forbidden"
        if action_type in self.approval_required:
            return "approval"
        if action_type in self.auto_allowed:
            return "auto"
        return "forbidden"

    def permissions(self, agent_id: str) -> AgentPermissions:
        return self.agents.get(agent_id, AgentPermissions())

    def check_tool(self, agent_id: str, tool: str) -> None:
        if tool not in self.permissions(agent_id).tools:
            raise PermissionDenied(f"Agent '{agent_id}' darf das Werkzeug '{tool}' nicht verwenden")

    def has_tool(self, agent_id: str, tool: str) -> bool:
        return tool in self.permissions(agent_id).tools


class Sandbox:
    """Erlaubt Dateizugriffe ausschließlich innerhalb des Workspace und der freigegebenen Unterordner."""

    def __init__(self, root: Path, policy: SecurityPolicy):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.policy = policy

    def resolve(self, rel_path: str) -> Path:
        if not rel_path or "\x00" in rel_path:
            raise PermissionDenied("Leerer oder ungültiger Pfad")
        candidate = Path(rel_path)
        if candidate.is_absolute() or rel_path.startswith(("~", "\\")) or re.match(r"^[A-Za-z]:", rel_path):
            raise PermissionDenied(f"Absolute Pfade sind nicht erlaubt: {rel_path}")
        if any(part == ".." for part in candidate.parts):
            raise PermissionDenied(f"Pfad verlässt den Workspace: {rel_path}")
        full = (self.root / candidate).resolve()
        if full != self.root and self.root not in full.parents:
            raise PermissionDenied(f"Pfad verlässt den Workspace: {rel_path}")
        return full

    def check_write(self, agent_id: str, rel_path: str) -> Path:
        self.policy.check_tool(agent_id, "workspace_write")
        full = self.resolve(rel_path)
        top = Path(rel_path).parts[0]
        if top not in self.policy.permissions(agent_id).write_dirs:
            raise PermissionDenied(f"Agent '{agent_id}' darf nicht in '{top}/' schreiben")
        # Symlinks im Pfad könnten aus dem Workspace hinausführen
        probe = full
        while probe != self.root:
            if probe.is_symlink():
                raise PermissionDenied(f"Symbolische Links sind nicht erlaubt: {rel_path}")
            probe = probe.parent
        return full

    def write_text(self, agent_id: str, rel_path: str, content: str, redactor: "Redactor") -> Path:
        full = self.check_write(agent_id, rel_path)
        data = redactor.redact(content).encode("utf-8")
        if len(data) > self.policy.limits.max_file_bytes:
            raise PermissionDenied(f"Datei zu groß ({len(data)} Bytes): {rel_path}")
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(data)
        return full

    def read_text(self, rel_path: str, max_bytes: int | None = None) -> str:
        full = self.resolve(rel_path)
        if not full.is_file():
            raise FileNotFoundError(rel_path)
        limit = max_bytes or self.policy.limits.max_file_view_bytes
        with full.open("rb") as fh:
            return fh.read(limit).decode("utf-8", errors="replace")


SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"(?i)(api[_-]?key|secret|password|passwort|token)\s*[:=]\s*['\"]?[A-Za-z0-9_\-\.]{12,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
]

SECRET_ENV_HINTS = ("KEY", "TOKEN", "SECRET", "PASSWORD")


class Redactor:
    """Entfernt bekannte Geheimnisse und typische Schlüsselmuster aus allem, was persistiert oder angezeigt wird."""

    def __init__(self, extra_secrets: list[str] | None = None):
        secrets = [v for k, v in os.environ.items() if any(h in k.upper() for h in SECRET_ENV_HINTS) and len(v) >= 8]
        secrets += [s for s in (extra_secrets or []) if s and len(s) >= 8]
        self.secrets = sorted(set(secrets), key=len, reverse=True)

    def add(self, secret: str) -> None:
        if secret and len(secret) >= 8 and secret not in self.secrets:
            self.secrets.append(secret)
            self.secrets.sort(key=len, reverse=True)

    def redact(self, text: str) -> str:
        if not text:
            return text
        for secret in self.secrets:
            text = text.replace(secret, "[REDACTED]")
        for pattern in SECRET_PATTERNS:
            text = pattern.sub("[REDACTED]", text)
        return text

    def redact_obj(self, value):
        if isinstance(value, str):
            return self.redact(value)
        if isinstance(value, list):
            return [self.redact_obj(v) for v in value]
        if isinstance(value, tuple):
            return tuple(self.redact_obj(v) for v in value)
        if isinstance(value, dict):
            return {k: self.redact_obj(v) for k, v in value.items()}
        return value

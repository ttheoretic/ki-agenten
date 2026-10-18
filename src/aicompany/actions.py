"""Externe Aktionen: Parameterschemas und Ausführer.

Ausführer erhalten ausschließlich die gespeicherten, genehmigten Parameter. Ohne konfigurierten
Anbieter führt das System nichts heimlich aus, sondern meldet ehrlich `manual_required`
(der Mensch führt die Aktion selbst aus und bestätigt sie im Freigabezentrum).
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from pydantic import BaseModel, Field, field_validator

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class PublishWebsiteParams(BaseModel):
    source_dir: str = Field(description="Workspace-relativer Ordner, z. B. site")
    target: Literal["local_release"] = "local_release"


class PublishContentParams(BaseModel):
    platform: str
    content_path: str
    scheduled_for: str | None = None


class SendMessageParams(BaseModel):
    channel: Literal["email"] = "email"
    recipients: list[str] = Field(min_length=1)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=5000)
    consent_basis: str = Field(min_length=5, description="Rechtsgrundlage, z. B. Einwilligung vom …")

    @field_validator("recipients")
    @classmethod
    def _valid_recipients(cls, v: list[str]) -> list[str]:
        bad = [r for r in v if not EMAIL_RE.match(r)]
        if bad:
            raise ValueError(f"Ungültige Empfänger: {bad}")
        if len(set(v)) != len(v):
            raise ValueError("Doppelte Empfänger")
        return v


class SpendParams(BaseModel):
    vendor: str
    description: str
    amount_eur: float = Field(ge=0)
    recurring: Literal["none", "monthly", "yearly"] = "none"


class GenericParams(BaseModel):
    description: str


PARAM_SCHEMAS: dict[str, type[BaseModel]] = {
    "publish_website": PublishWebsiteParams,
    "publish_content": PublishContentParams,
    "send_message": SendMessageParams,
    "paid_ads": SpendParams,
    "purchase": SpendParams,
    "subscription": SpendParams,
    "payment": SpendParams,
    "contract": GenericParams,
    "deploy_production": GenericParams,
    "process_personal_data": GenericParams,
    "request_permission": GenericParams,
}


@dataclass
class ExecutionContext:
    workspace: Path
    releases_dir: Path
    outbox_dir: Path
    approval_id: str


@dataclass
class ExecutionResult:
    status: Literal["succeeded", "failed", "manual_required"]
    message: str
    external_effect: bool
    details: dict


def _publish_website(params: PublishWebsiteParams, ctx: ExecutionContext) -> ExecutionResult:
    src = (ctx.workspace / params.source_dir).resolve()
    if ctx.workspace.resolve() not in src.parents or not src.is_dir():
        return ExecutionResult("failed", f"Quellordner nicht gefunden: {params.source_dir}", False, {})
    if not (src / "index.html").exists():
        return ExecutionResult("failed", "Keine index.html im Quellordner", False, {})
    dest = ctx.releases_dir / ctx.approval_id
    if dest.exists():  # idempotent: bereits ausgeführt
        return ExecutionResult("succeeded", f"Release existiert bereits: {dest}", False, {"release_dir": str(dest)})
    shutil.copytree(src, dest)
    files = sorted(str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file())
    return ExecutionResult(
        "succeeded",
        "Website als lokales Release-Paket exportiert. Es ist KEIN öffentlicher Hoster konfiguriert – "
        "für eine echte Veröffentlichung das Paket manuell hochladen.",
        False, {"release_dir": str(dest), "files": files},
    )


def _send_message(params: SendMessageParams, ctx: ExecutionContext) -> ExecutionResult:
    ctx.outbox_dir.mkdir(parents=True, exist_ok=True)
    path = ctx.outbox_dir / f"{ctx.approval_id}.eml"
    if not path.exists():
        body = (f"To: {', '.join(params.recipients)}\nSubject: {params.subject}\nX-Consent-Basis: {params.consent_basis}\n\n"
                f"{params.body}\n")
        path.write_text(body, encoding="utf-8")
    return ExecutionResult(
        "manual_required",
        "Kein Versandanbieter konfiguriert: Nachricht liegt im lokalen Postausgang und wurde NICHT versendet.",
        False, {"outbox_file": str(path), "recipients": len(params.recipients)},
    )


def _manual(action: str) -> Callable[[BaseModel, ExecutionContext], ExecutionResult]:
    def run(params: BaseModel, ctx: ExecutionContext) -> ExecutionResult:
        return ExecutionResult(
            "manual_required",
            f"Für '{action}' ist bewusst keine automatische Ausführung implementiert (keine Zahlungs-/Plattformzugänge). "
            "Bitte manuell ausführen und anschließend im Freigabezentrum bestätigen.",
            False, {"params": params.model_dump()},
        )
    return run


EXECUTORS: dict[str, Callable[[BaseModel, ExecutionContext], ExecutionResult]] = {
    "publish_website": _publish_website,  # type: ignore[dict-item]
    "send_message": _send_message,  # type: ignore[dict-item]
    **{a: _manual(a) for a in PARAM_SCHEMAS if a not in ("publish_website", "send_message")},
}

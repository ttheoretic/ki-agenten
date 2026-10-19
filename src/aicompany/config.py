"""Zentrale Konfiguration: settings.toml + Umgebungsvariablen, validiert mit Pydantic."""
from __future__ import annotations

import hashlib
import os
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "settings.toml"
DEFAULT_SECURITY = PROJECT_ROOT / "config" / "security.toml"

Mode = Literal["dry_run", "live"]


class CompanyConfig(BaseModel):
    goal: str
    name: str = "KI-Agenten Unternehmen"


class BudgetConfig(BaseModel):
    monthly_total_eur: float = Field(100.0, gt=0)
    monthly_api_eur: float = Field(30.0, gt=0)
    per_run_eur: float = Field(2.0, gt=0)
    max_agent_calls_per_run: int = Field(20, ge=1)
    max_revisions_per_task: int = Field(2, ge=0)
    max_attempts_per_call: int = Field(2, ge=1, le=5)
    warn_thresholds: list[float] = [0.5, 0.75, 0.9]
    usd_to_eur: float = 0.92
    uncertainty_markup: float = Field(1.25, ge=1.0)


class ModelPrice(BaseModel):
    input_per_mtok_usd: float = Field(ge=0)
    output_per_mtok_usd: float = Field(ge=0)


class ModelsConfig(BaseModel):
    default: str = "gpt-5.4-mini"
    escalation: str = "gpt-5.4"
    allow_escalation: bool = True
    disable_tracing: bool = True


class AgentLimits(BaseModel):
    model: str | None = None
    max_output_tokens: int = Field(3000, ge=256)
    max_input_tokens: int = Field(10000, ge=1000)


class WebSearchConfig(BaseModel):
    enabled: bool = True
    max_calls_per_run: int = 8
    cost_per_call_usd: float = 0.01
    estimated_calls_per_research_task: int = 4


class OrchestratorConfig(BaseModel):
    concurrency: int = Field(3, ge=1, le=8)
    ceo_review_each_run: bool = True
    max_followup_tasks: int = 2
    retry_backoff_seconds: float = 2.0
    run_stale_after_seconds: int = 900
    call_timeout_seconds: int = 180


class CollaborationConfig(BaseModel):
    enabled: bool = True
    max_consultations_per_run: int = Field(4, ge=0)
    max_blocking_help_per_task: int = Field(1, ge=0)
    offer_help_on_revision: bool = True


class BuilderConfig(BaseModel):
    execution: Literal["auto", "docker", "subprocess", "off"] = "auto"
    test_timeout_seconds: int = Field(90, ge=10, le=600)
    max_turns: int = Field(30, ge=4, le=80)
    agentic_cost_factor: float = Field(8.0, ge=1.0)
    max_files: int = Field(60, ge=5, le=300)


class ExperimentConfig(BaseModel):
    days: int = 30
    clock: Literal["calendar", "accelerated"] = "calendar"
    days_per_run: int = 5
    min_idea_score: float = 55
    max_cycles: int = Field(12, ge=1)


class ApprovalsConfig(BaseModel):
    default_expiry_hours: int = 168
    max_recipients_per_message: int = 25


class SchedulerConfig(BaseModel):
    interval_minutes: int = Field(360, ge=5)
    max_runs_per_day: int = Field(4, ge=1)


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8765


class Settings(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    mode: Mode = "dry_run"
    data_dir: Path
    config_path: Path = DEFAULT_CONFIG
    security_path: Path = DEFAULT_SECURITY
    company: CompanyConfig
    budget: BudgetConfig = BudgetConfig()
    models: ModelsConfig = ModelsConfig()
    pricing: dict[str, ModelPrice] = {}
    agents: dict[str, AgentLimits] = {}
    web_search: WebSearchConfig = WebSearchConfig()
    orchestrator: OrchestratorConfig = OrchestratorConfig()
    experiment: ExperimentConfig = ExperimentConfig()
    collaboration: CollaborationConfig = CollaborationConfig()
    builder: BuilderConfig = BuilderConfig()
    approvals: ApprovalsConfig = ApprovalsConfig()
    scheduler: SchedulerConfig = SchedulerConfig()
    server: ServerConfig = ServerConfig()

    @property
    def db_path(self) -> Path:
        return self.data_dir / "company.db"

    @property
    def workspace_dir(self) -> Path:
        return self.data_dir / "workspace"

    @property
    def releases_dir(self) -> Path:
        return self.data_dir / "releases"

    @property
    def outbox_dir(self) -> Path:
        return self.data_dir / "outbox"

    @property
    def token_path(self) -> Path:
        return self.data_dir / "owner_token"

    def agent_limits(self, agent_id: str) -> AgentLimits:
        return self.agents.get(agent_id, AgentLimits())

    def model_for(self, agent_id: str) -> str:
        if self.mode == "dry_run":
            return "mock-model"
        return self.agent_limits(agent_id).model or self.models.default

    def fingerprint(self) -> str:
        return hashlib.sha256(self.config_path.read_bytes()).hexdigest()[:16]


def load_env_file(path: Path) -> None:
    """Minimaler .env-Loader (ohne Zusatzabhängigkeit). Bestehende Umgebungsvariablen haben Vorrang."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


def load_settings(
    config_path: Path | str | None = None,
    *,
    mode: Mode | None = None,
    data_dir: Path | str | None = None,
    overrides: dict | None = None,
) -> Settings:
    load_env_file(PROJECT_ROOT / ".env")
    path = Path(config_path or os.environ.get("AICO_CONFIG") or DEFAULT_CONFIG)
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    resolved_mode: Mode = mode or os.environ.get("AICO_MODE", "dry_run")  # type: ignore[assignment]
    if resolved_mode not in ("dry_run", "live"):
        raise ValueError(f"Ungültiger Modus: {resolved_mode}")
    ddir = Path(data_dir or os.environ.get("AICO_DATA_DIR") or PROJECT_ROOT / "data" / resolved_mode)
    raw.update(overrides or {})
    if resolved_mode == "dry_run":
        # Dry-Run: beschleunigte Uhr, damit ein kompletter 30-Tage-Zyklus durchlaufen werden kann
        raw.setdefault("experiment", {}).setdefault("clock", "accelerated")
        if (overrides or {}).get("experiment", {}).get("clock") is None:
            raw["experiment"]["clock"] = "accelerated"
    return Settings(mode=resolved_mode, data_dir=ddir.resolve(), config_path=path, **raw)

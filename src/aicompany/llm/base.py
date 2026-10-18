"""Austauschbare LLM-Backend-Schnittstelle (Dry-Run-Simulation oder OpenAI Agents SDK)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel

from ..budget import CallUsage


class LLMTransientError(Exception):
    """Vorübergehender Fehler (Netzwerk, Rate-Limit, Timeout, 5xx) – darf begrenzt wiederholt werden."""


class LLMOutputError(Exception):
    """Ausgabe entspricht nicht dem geforderten Schema."""


class LLMFatalError(Exception):
    """Nicht wiederholbarer Fehler (z. B. fehlender Schlüssel, ungültiges Modell)."""


@dataclass
class AgentCall:
    agent_id: str
    task_id: str
    task_key: str
    kind: str
    instructions: str
    prompt: str
    output_type: type[BaseModel]
    model: str
    max_output_tokens: int
    tools: list[str]
    context: dict[str, Any] = field(default_factory=dict)  # strukturierte Eingaben (für Simulation)
    revision: int = 0
    feedback: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AgentCallResult:
    output: BaseModel
    usage: CallUsage | None
    model: str
    simulated: bool
    cited_urls: list[str] = field(default_factory=list)
    web_search_calls: int = 0


class LLMBackend(Protocol):
    name: str
    simulated: bool

    async def run(self, call: AgentCall) -> AgentCallResult: ...

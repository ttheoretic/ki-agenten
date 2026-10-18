"""FastAPI-Backend des Control-Centers: REST für Abfragen/Steuerung, Server-Sent Events für Live-Ereignisse.

Alle Endpunkte außer /api/health verlangen das Owner-Token (Header `Authorization: Bearer …`,
für EventSource/Dateiansicht alternativ `?token=`). Sämtliche Freigaben und Steuerungsaktionen
werden serverseitig validiert und protokolliert – das UI kann keine Prüfung umgehen.
"""
from __future__ import annotations

import asyncio
import hmac
import json
import re
import threading
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..agents.roles import ROLES
from ..approvals import ApprovalError
from ..company import Company
from ..config import PROJECT_ROOT
from ..db import now_iso
from ..events import COMM_TYPES
from ..orchestrator import Orchestrator, RunActive
from ..reports import write_report
from ..state import agent_detail, company_snapshot, task_brief
from ..tasks import InvalidTransition

FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
METRIC_NAME = re.compile(r"^[a-z][a-z0-9_]{1,39}$")


class DecisionIn(BaseModel):
    decision: Literal["approve", "reject", "request_info", "defer"]
    params_hash: str | None = None
    note: str = Field("", max_length=2000)


class ManualConfirmIn(BaseModel):
    executed: bool
    actual_cost_eur: float = Field(0.0, ge=0)
    note: str = Field("", max_length=2000)


class MetricIn(BaseModel):
    name: str
    value: float
    unit: str = Field("", max_length=20)
    note: str = Field("", max_length=500)


class RunManager:
    """Startet Geschäftsläufe im Hintergrund; der DB-Lock verhindert parallele Läufe auch prozessübergreifend."""

    def __init__(self, company: Company):
        self.company = company
        self.thread: threading.Thread | None = None
        self.last_error: str | None = None

    def busy(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def start(self, trigger: str) -> None:
        if self.busy():
            raise RunActive("In diesem Server läuft bereits ein Geschäftslauf")

        def target():
            try:
                asyncio.run(Orchestrator(self.company).run_once(trigger))
                self.last_error = None
            except RunActive as exc:
                self.last_error = str(exc)
            except Exception as exc:  # wird im Ereignisstrom sichtbar
                self.last_error = str(exc)
                self.company.events.emit("run.error", f"Lauf konnte nicht gestartet werden: {exc}", severity="error")

        self.thread = threading.Thread(target=target, daemon=True, name="business-run")
        self.thread.start()


def create_app(company: Company) -> FastAPI:
    app = FastAPI(title="KI-Unternehmen Control-Center", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None)
    host = company.settings.server.host
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=sorted({"127.0.0.1", "localhost", "testserver", host}))
    runs = RunManager(company)
    app.state.company = company
    app.state.runs = runs

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'",
        )
        return response

    def auth(request: Request, token: str | None = Query(None)) -> str:
        header = request.headers.get("authorization", "")
        supplied = header[7:] if header.lower().startswith("bearer ") else (token or "")
        if not supplied or not hmac.compare_digest(supplied, company.owner_token):
            raise HTTPException(401, "Owner-Token fehlt oder ist ungültig")
        return "owner"

    # ---------- Lesen ----------
    @app.get("/api/health")
    def health():
        return {"ok": True, "mode": company.settings.mode, "time": now_iso()}

    @app.get("/api/state")
    def state(_: str = Depends(auth)):
        snap = company_snapshot(company)
        snap["server"] = {"run_thread_busy": runs.busy(), "last_run_error": runs.last_error}
        return snap

    @app.get("/api/agents/{agent_id}")
    def get_agent(agent_id: str, _: str = Depends(auth)):
        if agent_id not in ROLES:
            raise HTTPException(404, "Unbekannter Agent")
        return agent_detail(company, agent_id)

    @app.get("/api/tasks")
    def list_tasks(agent: str | None = None, status: str | None = None, _: str = Depends(auth)):
        return [task_brief(t) for t in company.tasks.list(agent=agent, status=status)]

    @app.get("/api/tasks/{task_id}")
    def get_task(task_id: str, _: str = Depends(auth)):
        t = company.tasks.get(task_id)
        if not t:
            raise HTTPException(404, "Aufgabe nicht gefunden")
        return t.model_dump()

    @app.get("/api/events")
    def list_events(after_id: int = 0, limit: int = 200, agent: str | None = None, type: str | None = None,
                    severity: str | None = None, since: str | None = None, until: str | None = None,
                    task_id: str | None = None, latest: bool = False, _: str = Depends(auth)):
        types = [t.strip() for t in type.split(",")] if type else None
        evs = company.events.list(after_id=after_id, limit=limit, agent=agent, types=types, severity=severity, since=since,
                                  until=until, task_id=task_id, descending=latest)
        if latest:
            evs = list(reversed(evs))
        return [e.model_dump() for e in evs]

    # muss vor /api/events/{event_id} registriert werden
    @app.get("/api/events/stream")
    async def stream(request: Request, after_id: int | None = None, max_seconds: float | None = Query(None, gt=0, le=3600),
                     _: str = Depends(auth)):
        last_header = request.headers.get("last-event-id")
        cursor = int(last_header) if last_header and last_header.isdigit() else (after_id if after_id is not None else company.events.last_id())

        async def gen():
            nonlocal cursor
            yield f"retry: 2000\nevent: hello\ndata: {json.dumps({'last_event_id': company.events.last_id()})}\n\n"
            idle = 0
            loop = asyncio.get_running_loop()
            deadline = loop.time() + max_seconds if max_seconds else None
            while not await request.is_disconnected():
                if deadline and loop.time() > deadline:
                    break  # Client verbindet sich automatisch neu (Last-Event-ID)
                events = await asyncio.to_thread(company.events.list, after_id=cursor, limit=200)
                for e in events:
                    cursor = e.id
                    yield f"id: {e.id}\nevent: ev\ndata: {e.model_dump_json()}\n\n"
                if events:
                    idle = 0
                else:
                    idle += 1
                    if idle % 30 == 0:
                        yield ": ping\n\n"
                await asyncio.sleep(0.5)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/events/{event_id}")
    def get_event(event_id: int, _: str = Depends(auth)):
        e = company.events.get(event_id)
        if not e:
            raise HTTPException(404, "Ereignis nicht gefunden")
        related_task = company.tasks.get(e.task_id) if e.task_id else None
        return {"event": e.model_dump(), "task": task_brief(related_task) if related_task else None,
                "approval": company.approvals.get(e.approval_id).model_dump() if e.approval_id and company.approvals.get(e.approval_id) else None}

    @app.get("/api/communications")
    def communications(a: str, b: str, limit: int = 50, _: str = Depends(auth)):
        rows = company.db.query(
            f"SELECT id FROM events WHERE type IN ({','.join('?' * len(COMM_TYPES))}) AND ((from_agent=? AND to_agent=?) OR (from_agent=? AND to_agent=?))"
            " ORDER BY id DESC LIMIT ?", (*COMM_TYPES, a, b, b, a, limit))
        result = []
        for r in rows:
            e = company.events.get(r["id"])
            t = company.tasks.get(e.task_id) if e.task_id else None
            result.append({"event": e.model_dump(), "task": task_brief(t) if t else None})
        return result

    @app.get("/api/approvals")
    def list_approvals(status: str | None = None, _: str = Depends(auth)):
        return [a.model_dump() for a in company.approvals.list(status)]

    @app.get("/api/costs")
    def costs(_: str = Depends(auth)):
        return {"summary": company.budget.summary(), "by_agent": company.budget.by_agent(),
                "records": [dict(r) for r in company.db.query("SELECT * FROM cost_records ORDER BY id DESC LIMIT 200")]}

    @app.get("/api/runs")
    def list_runs(_: str = Depends(auth)):
        return [dict(r) for r in company.db.query("SELECT * FROM runs ORDER BY started_at DESC LIMIT 50")]

    @app.get("/api/files")
    def files(_: str = Depends(auth)):
        return [dict(r) for r in company.db.query("SELECT * FROM artifacts ORDER BY created_at DESC")]

    @app.get("/api/files/content")
    def file_content(path: str, _: str = Depends(auth)):
        try:
            text = company.sandbox.read_text(path)
        except FileNotFoundError:
            raise HTTPException(404, "Datei nicht gefunden")
        except Exception:
            raise HTTPException(403, "Zugriff außerhalb des Workspace verweigert")
        # Immer als reiner Text ausliefern und jegliche Ausführung im Browser unterbinden
        return PlainTextResponse(company.redactor.redact(text), headers={
            "Content-Security-Policy": "sandbox; default-src 'none'", "Content-Disposition": "inline"})

    @app.get("/api/metrics")
    def metrics(_: str = Depends(auth)):
        return [dict(r) for r in company.db.query("SELECT * FROM metrics ORDER BY ts DESC")]

    @app.get("/api/audit")
    def audit(_: str = Depends(auth)):
        return [dict(r) for r in company.db.query("SELECT * FROM audit_log ORDER BY id DESC LIMIT 200")]

    # ---------- Ändern ----------
    @app.post("/api/approvals/{approval_id}/decision")
    def decide(approval_id: str, body: DecisionIn, actor: str = Depends(auth)):
        try:
            ap = company.approvals.decide(approval_id, body.decision, actor=actor, confirmed_hash=body.params_hash, note=body.note)
            if ap.status == "approved":
                ap = company.approvals.execute(approval_id, actor=actor)
        except ApprovalError as exc:
            raise HTTPException(409, str(exc))
        return ap.model_dump()

    @app.post("/api/approvals/{approval_id}/confirm-manual")
    def confirm_manual(approval_id: str, body: ManualConfirmIn, actor: str = Depends(auth)):
        try:
            return company.approvals.confirm_manual(approval_id, actor=actor, executed=body.executed,
                                                    actual_cost_eur=body.actual_cost_eur, note=body.note).model_dump()
        except ApprovalError as exc:
            raise HTTPException(409, str(exc))

    @app.post("/api/approvals/{approval_id}/execute")
    def execute(approval_id: str, actor: str = Depends(auth)):
        try:
            return company.approvals.execute(approval_id, actor=actor).model_dump()
        except ApprovalError as exc:
            raise HTTPException(409, str(exc))

    @app.post("/api/control/{action}")
    def control(action: Literal["pause", "resume", "stop_new", "stop"], actor: str = Depends(auth)):
        flags = company.control.apply(action, actor)
        return {"flags": flags, "status": company.control.company_status()}

    @app.post("/api/agents/{agent_id}/{action}")
    def agent_control(agent_id: str, action: Literal["pause", "resume"], actor: str = Depends(auth)):
        if agent_id not in ROLES:
            raise HTTPException(404, "Unbekannter Agent")
        company.control.set_agent_paused(agent_id, action == "pause", actor)
        return {"agent": agent_id, "paused": agent_id in company.control.paused_agents()}

    @app.post("/api/tasks/{task_id}/retry")
    def retry(task_id: str, actor: str = Depends(auth)):
        try:
            t = company.tasks.retry(task_id, actor)
        except InvalidTransition as exc:
            raise HTTPException(409, str(exc))
        company.db.audit(actor, "task.retry", task_id)
        company.events.emit("task.retry", f"Eigentümer startet Aufgabe neu: {t.title}", agent=t.agent, task_id=t.id)
        return task_brief(t)

    @app.post("/api/runs")
    def start_run(actor: str = Depends(auth)):
        ok, reason = company.control.may_dispatch()
        if not ok:
            raise HTTPException(409, f"Lauf nicht möglich: {reason}")
        if company.budget.exhausted():
            raise HTTPException(409, "Lauf nicht möglich: Budget ausgeschöpft")
        try:
            runs.start("control-center")
        except RunActive as exc:
            raise HTTPException(409, str(exc))
        company.db.audit(actor, "run.start", None)
        return {"started": True}

    @app.post("/api/reports")
    def make_report(actor: str = Depends(auth)):
        path = write_report(company, title="Statusbericht (angefordert)")
        company.db.audit(actor, "report.request", path)
        return {"path": path, "content": company.sandbox.read_text(path)}

    @app.post("/api/metrics")
    def add_metric(body: MetricIn, actor: str = Depends(auth)):
        if not METRIC_NAME.match(body.name):
            raise HTTPException(422, "Kennzahlname: Kleinbuchstaben, Ziffern, Unterstrich (z. B. visitors, sales, revenue_eur)")
        company.db.execute("INSERT INTO metrics(ts, name, value, unit, source, note) VALUES (?,?,?,?,?,?)",
                           (now_iso(), body.name, body.value, body.unit, "manual", company.redactor.redact(body.note)))
        company.db.audit(actor, "metric.add", body.name, body.model_dump())
        company.events.emit("metric.recorded", f"Kennzahl erfasst: {body.name} = {body.value} {body.unit}", agent="analytics",
                            data={"name": body.name, "value": body.value, "source": "manual"})
        return {"ok": True}

    # ---------- Frontend ----------
    if FRONTEND_DIST.exists():
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
    else:
        @app.get("/", response_class=HTMLResponse)
        def no_frontend():
            return ("<h1>Control-Center nicht gebaut</h1><p>Bitte <code>cd frontend && npm install && npm run build</code> ausführen."
                    " Die API läuft unter /api.</p>")

    @app.exception_handler(InvalidTransition)
    async def invalid_transition(_, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    return app

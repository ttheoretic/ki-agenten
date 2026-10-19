"""Control-Center-Backend: Live-Daten, Ereignisstrom, Freigaben, Steuerung, Fehlerzustände."""
import json
import time

import pytest
from fastapi.testclient import TestClient

from aicompany.api.app import create_app

from conftest import run, run_until_finished


@pytest.fixture
def client(company):
    c = TestClient(create_app(company))
    c.headers["Authorization"] = f"Bearer {company.owner_token}"
    return c


def test_auth_required(company):
    anon = TestClient(create_app(company))
    assert anon.get("/api/health").status_code == 200
    assert anon.get("/api/state").status_code == 401
    assert anon.get("/api/state", headers={"Authorization": "Bearer falsch"}).status_code == 401
    assert anon.post("/api/control/pause").status_code == 401
    assert anon.get(f"/api/state?token={company.owner_token}").status_code == 200


def test_initial_state_has_no_fake_data(client):
    s = client.get("/api/state").json()
    assert s["company"]["status"] == "not_started"
    assert s["experiment"]["day"] == 0
    assert s["selected_idea"] is None
    assert s["metrics"] == [] and s["finance_actuals"]["revenue_eur"] is None
    assert s["progress"]["percent"] is None
    assert len(s["agents"]) == 11
    assert all(a["status"] == "idle" and a["current_task"] is None for a in s["agents"])
    assert s["simulated"] is True


def test_state_reflects_real_status(client, company):
    run(company)
    s = client.get("/api/state").json()
    by = {a["id"]: a for a in s["agents"]}
    assert s["selected_idea"]["id"] == "angebotsrechner-handwerk"
    assert by["research"]["progress"] == {"completed": 1, "total": 1}
    assert by["research"]["cost_eur"] > 0
    assert s["progress"]["completed"] == len([t for t in s["tasks"] if t["status"] == "completed" and not t["key"].startswith(("ceo.review", "help.", "followup."))])
    assert any(m["achieved"] for m in s["milestones"])
    for a in s["agents"]:
        mine = [t for t in s["tasks"] if t["agent"] == a["id"]]
        if a["status"] == "done":
            assert mine and all(t["status"] == "completed" for t in mine)


def test_agent_detail(client, company):
    run(company)
    d = client.get("/api/agents/builder").json()
    assert d["tools"] == ["workspace_read", "workspace_write", "local_static_checks"]
    assert d["completed_tasks"] or d["queue"]
    assert any(e["to_agent"] == "builder" for e in d["communications"])
    assert client.get("/api/agents/nobody").status_code == 404


def test_events_persist_and_paginate(client, company):
    run(company)
    all_events = client.get("/api/events?limit=2000").json()
    assert all_events == sorted(all_events, key=lambda e: e["id"])
    mid = all_events[len(all_events) // 2]["id"]
    after = client.get(f"/api/events?after_id={mid}&limit=2000").json()
    assert all(e["id"] > mid for e in after)
    assert len(after) == len([e for e in all_events if e["id"] > mid])
    filt = client.get("/api/events?agent=qa&severity=warning").json()
    assert all("qa" in (e["agent"], e["from_agent"], e["to_agent"]) for e in filt)
    comm = client.get("/api/events?type=comm.*").json()
    assert comm and all(e["from_agent"] and e["to_agent"] for e in comm)
    detail = client.get(f"/api/events/{comm[0]['id']}").json()
    assert detail["event"]["id"] == comm[0]["id"]


def test_events_survive_restart(make_company, tmp_path):
    c1 = make_company(data_dir=tmp_path / "persist")
    run(c1)
    n = c1.events.last_id()
    c2 = make_company(data_dir=tmp_path / "persist")  # "Neustart": neue Instanz, gleiche DB
    cl = TestClient(create_app(c2))
    cl.headers["Authorization"] = f"Bearer {c2.owner_token}"
    assert c2.owner_token == c1.owner_token
    assert cl.get("/api/state").json()["last_event_id"] == n
    assert len(cl.get("/api/events?limit=2000").json()) == n


def _read_sse(client, url, headers=None):
    events = []
    with client.stream("GET", url, headers=headers or {}) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        buf = {}
        for line in r.iter_lines():
            if line.startswith("id: "):
                buf["id"] = int(line[4:])
            elif line.startswith("event: "):
                buf["event"] = line[7:]
            elif line.startswith("data: "):
                buf["data"] = json.loads(line[6:])
            elif line == "" and buf:
                events.append(buf)
                buf = {}
    return events


def test_sse_stream_and_reconnect(client, company):
    company.events.emit("test.a", "eins")
    company.events.emit("test.b", "zwei")
    first = company.events.last_id() - 2
    evs = _read_sse(client, f"/api/events/stream?after_id={first}&max_seconds=1")
    ids = [e["id"] for e in evs if e.get("event") == "ev"]
    assert ids == [first + 1, first + 2]
    company.events.emit("test.c", "drei")
    # Wiederverbindung mit Last-Event-ID liefert nur neuere Ereignisse – keine Duplikate
    again = _read_sse(client, "/api/events/stream?max_seconds=1", headers={"Last-Event-ID": str(ids[-1])})
    assert [e["id"] for e in again if e.get("event") == "ev"] == [ids[-1] + 1]


def test_approval_flow_via_api(client, company):
    run_until_finished(company)
    aps = client.get("/api/approvals?status=open").json()
    web = next(a for a in aps if a["action_type"] == "publish_website")
    # Genehmigung nur mit dem angezeigten Hash
    r = client.post(f"/api/approvals/{web['id']}/decision", json={"decision": "approve"})
    assert r.status_code == 409
    r = client.post(f"/api/approvals/{web['id']}/decision", json={"decision": "approve", "params_hash": web["params_hash"]})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "approved" and body["execution_status"] == "succeeded"
    assert body["execution_result"]["external_effect"] is False
    # Doppelte Genehmigung/Ausführung wird abgewiesen bzw. ist idempotent
    assert client.post(f"/api/approvals/{web['id']}/decision", json={"decision": "approve", "params_hash": web["params_hash"]}).status_code == 409
    assert client.post(f"/api/approvals/{web['id']}/execute").json()["execution_status"] == "succeeded"
    assert len(company.events.list(types=["approval.executing"])) == 1
    ads = next(a for a in aps if a["action_type"] == "paid_ads")
    r = client.post(f"/api/approvals/{ads['id']}/decision", json={"decision": "reject", "note": "erst organisch testen"})
    assert r.json()["status"] == "rejected"
    audit = client.get("/api/audit").json()
    assert {a["action"] for a in audit} >= {"approval.approve", "approval.reject", "approval.execute"}


def test_control_endpoints(client, company):
    assert client.post("/api/control/pause").json()["status"] == "paused"
    assert client.post("/api/runs").status_code == 409
    assert client.get("/api/state").json()["company"]["status"] == "paused"
    assert client.post("/api/control/resume").json()["status"] == "active"
    assert client.post("/api/control/stop").json()["status"] == "stopped"
    assert client.post("/api/control/explode").status_code == 422
    client.post("/api/control/resume")
    assert client.post("/api/agents/qa/pause").json()["paused"] is True
    s = client.get("/api/state").json()
    assert next(a for a in s["agents"] if a["id"] == "qa")["status"] == "paused"
    assert client.post("/api/agents/qa/resume").json()["paused"] is False


def test_start_run_via_api(client, company):
    assert client.post("/api/runs").json()["started"] is True
    deadline = time.time() + 20
    while time.time() < deadline:
        s = client.get("/api/state").json()
        if s["last_run"] and s["last_run"]["status"] != "running":
            break
        time.sleep(0.2)
    assert s["last_run"]["status"] == "completed"
    assert s["selected_idea"] is not None


def test_retry_failed_task(client, company):
    from aicompany.llm.mock import MockBackend
    company._backend = MockBackend(invalid_plan={"p1.research.opportunities": 3})
    run(company)
    t = company.tasks.get_by_key("p1.research.opportunities")
    assert t.status == "failed"
    s = client.get("/api/state").json()
    assert s["company"]["status"] == "attention" and s["blockers"]
    assert next(a for a in s["agents"] if a["id"] == "research")["status"] == "error"
    r = client.post(f"/api/tasks/{t.id}/retry")
    assert r.json()["status"] == "pending"
    assert client.post(f"/api/tasks/{t.id}/retry").status_code == 409


def test_file_access_is_sandboxed(client, company):
    run(company)
    files = client.get("/api/files").json()
    assert files
    r = client.get("/api/files/content", params={"path": files[0]["path"]})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert "sandbox" in r.headers["content-security-policy"]
    assert client.get("/api/files/content", params={"path": "../company.db"}).status_code == 403
    assert client.get("/api/files/content", params={"path": "/etc/passwd"}).status_code == 403


def test_metrics_input_validated(client):
    assert client.post("/api/metrics", json={"name": "Besucher!", "value": 1}).status_code == 422
    assert client.post("/api/metrics", json={"name": "visitors", "value": 42}).status_code == 200
    s = client.get("/api/state").json()
    assert s["metrics"][0]["name"] == "visitors" and s["metrics"][0]["source"] == "manual"


def test_report_on_demand(client, company):
    run(company)
    r = client.post("/api/reports").json()
    assert "Managementbericht" in r["content"] or "Statusbericht" in r["content"]
    assert "Noch keine Daten" in r["content"]


def test_communications_between_agents(client, company):
    run(company)
    comms = client.get("/api/communications", params={"a": "ceo", "b": "research"}).json()
    assert comms and comms[0]["event"]["type"].startswith("comm.")


def test_security_headers(client):
    r = client.get("/api/health")
    assert r.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in r.headers["content-security-policy"]


def test_untrusted_host_rejected(company):
    c = TestClient(create_app(company), base_url="http://evil.example")
    assert c.get("/api/health").status_code == 400

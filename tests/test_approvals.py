"""Freigabezentrum: Validierung, Hash-Bindung, Idempotenz, Budget, Steuerung."""
import pytest

from aicompany.approvals import ApprovalError

from conftest import run_until_finished


def make_site(company):
    site = company.settings.workspace_dir / "site"
    site.mkdir(parents=True, exist_ok=True)
    (site / "index.html").write_text("<html><title>x</title></html>")


def publish(company, **kw):
    args = dict(agent="operations", task_id="T-1", action_type="publish_website", title="Website veröffentlichen",
                description="d", justification="j", expected_benefit="b", params={"source_dir": "site"})
    args.update(kw)
    return company.approvals.create(**args)


def test_forbidden_and_unknown_actions_rejected(company):
    with pytest.raises(ApprovalError):
        publish(company, action_type="shell_exec", params={})
    with pytest.raises(ApprovalError):
        publish(company, action_type="something_new", params={})
    assert company.events.list(types=["security.violation"])


def test_internal_actions_need_no_request(company):
    with pytest.raises(ApprovalError, match="intern"):
        publish(company, action_type="workspace_write", params={})


def test_mass_messages_rejected(company):
    recipients = [f"p{i}@example.org" for i in range(company.settings.approvals.max_recipients_per_message + 1)]
    with pytest.raises(ApprovalError, match="Massenkommunikation"):
        publish(company, action_type="send_message", params={"recipients": recipients, "subject": "s", "body": "b",
                                                              "consent_basis": "Einwilligung vom 01.01."})


def test_duplicate_requests_are_deduplicated(company):
    a1 = publish(company)
    a2 = publish(company)
    assert a1.id == a2.id
    assert len(company.approvals.list()) == 1


def test_approval_requires_matching_hash(company):
    ap = publish(company)
    with pytest.raises(ApprovalError, match="Hash"):
        company.approvals.decide(ap.id, "approve", actor="owner", confirmed_hash=None)
    with pytest.raises(ApprovalError, match="Hash"):
        company.approvals.decide(ap.id, "approve", actor="owner", confirmed_hash="0" * 64)
    assert company.approvals.get(ap.id).status == "pending"


def test_tampered_params_are_refused(company):
    ap = publish(company)
    company.db.execute("UPDATE approvals SET params=? WHERE id=?", ('{"source_dir": "../../etc", "target": "local_release"}', ap.id))
    with pytest.raises(ApprovalError, match="manipuliert"):
        company.approvals.decide(ap.id, "approve", actor="owner", confirmed_hash=ap.params_hash)


def test_approve_executes_exactly_once(company):
    make_site(company)
    ap = publish(company)
    company.approvals.decide(ap.id, "approve", actor="owner", confirmed_hash=ap.params_hash)
    assert company.approvals.get(ap.id).execution_status == "not_started"  # Genehmigung ≠ Ausführung
    r1 = company.approvals.execute(ap.id)
    r2 = company.approvals.execute(ap.id)
    assert r1.execution_status == r2.execution_status == "succeeded"
    assert r1.execution_result["external_effect"] is False  # ehrlich: nur lokales Release
    assert len(company.events.list(types=["approval.executing"])) == 1
    with pytest.raises(ApprovalError):
        company.approvals.decide(ap.id, "approve", actor="owner", confirmed_hash=ap.params_hash)


def test_reject_and_request_info(company):
    ap = publish(company)
    company.approvals.decide(ap.id, "request_info", actor="owner", confirmed_hash=None, note="Ist das Impressum ausgefüllt?")
    assert company.approvals.get(ap.id).status == "info_requested"
    company.approvals.decide(ap.id, "reject", actor="owner", confirmed_hash=None)
    assert company.approvals.get(ap.id).status == "rejected"
    with pytest.raises(ApprovalError):
        company.approvals.execute(ap.id)
    assert company.db.query("SELECT * FROM audit_log WHERE target=?", (ap.id,))


def test_expired_requests_cannot_be_approved(company):
    ap = publish(company)
    company.db.execute("UPDATE approvals SET expires_at='2000-01-01T00:00:00' WHERE id=?", (ap.id,))
    with pytest.raises(ApprovalError, match="entschieden"):
        company.approvals.decide(ap.id, "approve", actor="owner", confirmed_hash=ap.params_hash)
    assert company.approvals.get(ap.id).status == "expired"


def test_spend_over_budget_refused(company):
    amount = company.settings.budget.monthly_total_eur + 1
    ap = publish(company, action_type="paid_ads", cost_eur=amount,
                 params={"vendor": "x", "description": "y", "amount_eur": amount, "recurring": "none"})
    assert ap.budget_impact["fits_budget"] is False
    with pytest.raises(ApprovalError, match="Restbudget"):
        company.approvals.decide(ap.id, "approve", actor="owner", confirmed_hash=ap.params_hash)


def test_amount_mismatch_rejected(company):
    with pytest.raises(ApprovalError, match="stimmen nicht"):
        publish(company, action_type="purchase", cost_eur=5, params={"vendor": "x", "description": "y", "amount_eur": 50})


def test_spend_requires_manual_execution_and_confirmation(company):
    ap = publish(company, action_type="paid_ads", cost_eur=15, params={"vendor": "x", "description": "y", "amount_eur": 15})
    company.approvals.decide(ap.id, "approve", actor="owner", confirmed_hash=ap.params_hash)
    assert company.budget.summary()["external_committed_eur"] == 15
    ex = company.approvals.execute(ap.id)
    assert ex.execution_status == "manual_required"  # das System zahlt niemals selbst
    with pytest.raises(ApprovalError, match="übersteigen"):
        company.approvals.confirm_manual(ap.id, actor="owner", executed=True, actual_cost_eur=20, note="")
    done = company.approvals.confirm_manual(ap.id, actor="owner", executed=True, actual_cost_eur=14.5, note="Rechnung 123")
    assert done.execution_status == "succeeded"
    assert company.budget.summary()["external_spent_eur"] == 14.5


def test_message_is_not_sent_without_provider(company):
    ap = publish(company, action_type="send_message", params={"recipients": ["a@example.org"], "subject": "Hallo", "body": "Text",
                                                               "consent_basis": "Anfrage vom 01.10."})
    company.approvals.decide(ap.id, "approve", actor="owner", confirmed_hash=ap.params_hash)
    ex = company.approvals.execute(ap.id)
    assert ex.execution_status == "manual_required"
    assert "NICHT versendet" in ex.execution_result["message"]


def test_execution_blocked_while_paused(company):
    make_site(company)
    ap = publish(company)
    company.approvals.decide(ap.id, "approve", actor="owner", confirmed_hash=ap.params_hash)
    company.control.apply("pause", "owner")
    assert company.approvals.execute(ap.id).execution_status == "not_started"
    company.control.apply("resume", "owner")
    assert company.approvals.execute(ap.id).execution_status == "succeeded"


def test_workflow_requests_approval_for_publication(company):
    run_until_finished(company)
    web = [a for a in company.approvals.list() if a.action_type == "publish_website"][0]
    assert web.agent == "operations" and web.task_id
    assert not company.settings.releases_dir.exists()  # nichts ohne Freigabe ausgeführt

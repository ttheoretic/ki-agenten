"""Berechtigungen, Sandbox und Schutz vertraulicher Daten."""
import os

import pytest

from aicompany.security import PermissionDenied, Redactor

from conftest import run


@pytest.mark.parametrize("path", ["../outside.txt", "/etc/passwd", "research/../../x", "~/x", "C:/x", ""])
def test_sandbox_rejects_escape(company, path):
    with pytest.raises(PermissionDenied):
        company.sandbox.check_write("research", path)


def test_agents_only_write_their_directories(company):
    company.sandbox.check_write("research", "research/a.md")
    with pytest.raises(PermissionDenied):
        company.sandbox.check_write("research", "site/index.html")
    with pytest.raises(PermissionDenied):
        company.sandbox.check_write("marketing", "product/app.js")


def test_symlink_escape_rejected(company, tmp_path):
    target = tmp_path / "secret"
    target.mkdir()
    link = company.settings.workspace_dir / "research"
    link.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(target, link)
    with pytest.raises(PermissionDenied):
        company.sandbox.check_write("research", "research/x.md")


def test_tool_permissions(company):
    company.policy.check_tool("research", "web_search")
    with pytest.raises(PermissionDenied):
        company.policy.check_tool("builder", "web_search")
    assert not any("shell" in t for p in company.policy.agents.values() for t in p.tools)


def test_policy_default_deny(company):
    assert company.policy.classify("publish_website") == "approval"
    assert company.policy.classify("modify_security_policy") == "forbidden"
    assert company.policy.classify("unknown_action") == "forbidden"


def test_config_is_outside_workspace(company):
    cfg = company.settings.security_path.resolve()
    assert company.sandbox.root not in cfg.parents


def test_redactor_masks_secrets(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-1234567890abcdefghij")
    r = Redactor()
    text = r.redact("Key ist sk-test-1234567890abcdefghij und api_key=abcdefghijklmnop123")
    assert "sk-test" not in text and "abcdefghijklmnop123" not in text


def test_secrets_never_persisted(monkeypatch, make_company):
    monkeypatch.setenv("SOME_SERVICE_TOKEN", "supersecretvalue-9876")
    c = make_company()
    c.events.emit("test", "Token supersecretvalue-9876 im Text", data={"nested": ["supersecretvalue-9876"]})
    c.sandbox.write_text("research", "research/leak.md", "supersecretvalue-9876", c.redactor)
    raw = c.settings.db_path.read_bytes()
    assert b"supersecretvalue-9876" not in raw
    assert "supersecretvalue-9876" not in (c.settings.workspace_dir / "research" / "leak.md").read_text()


def test_owner_token_not_in_events_or_files(company):
    run(company)
    token = company.owner_token.encode()
    assert token not in company.settings.db_path.read_bytes()
    for p in company.settings.workspace_dir.rglob("*"):
        if p.is_file():
            assert token not in p.read_bytes()


def test_policy_change_detected(tmp_path, make_company):
    src = make_company().settings.security_path.read_text()
    custom = tmp_path / "security.toml"
    custom.write_text(src)
    c = make_company(data_dir=tmp_path / "pc")
    c.settings.security_path = custom
    from aicompany.company import Company
    Company(c.settings, backend=c.backend)
    custom.write_text(src + "\n# geändert\n")
    Company(c.settings, backend=c.backend)
    assert c.events.list(types=["security.policy_changed"])

"""Tests for the Permission Guard — the security core."""
from __future__ import annotations

from app.security.permissions import (
    Decision,
    GuardRequest,
    PermissionGuard,
    PermissionPolicy,
)
from app.security.permissions import (
    PermissionLevel as P,
)


def guard(**kw) -> PermissionGuard:
    base = dict(
        allowed_paths=["/ws"],
        allowed_domains=["example.com"],
        command_allowlist=["ls", "cat"],
        command_blocklist=["rm -rf"],
    )
    base.update(kw)
    return PermissionGuard(**base)


def test_safe_read_auto_allows():
    g = guard()
    res = g.evaluate(GuardRequest("read_file", P.SAFE_READ))
    assert res.decision == Decision.AUTO_ALLOW


def test_browser_read_auto_allows():
    g = guard()
    res = g.evaluate(GuardRequest("open_url", P.BROWSER_READ, domain="example.com"))
    assert res.decision == Decision.AUTO_ALLOW


def test_always_approve_levels():
    g = guard()
    for level in (P.BROWSER_WRITE, P.DESKTOP_CONTROL, P.TERMINAL_WRITE,
                  P.CREDENTIAL_ACCESS, P.HIGH_RISK):
        res = g.evaluate(GuardRequest("t", level))
        assert res.decision == Decision.REQUIRES_APPROVAL, level


def test_credential_use_always_requires_approval():
    g = guard()
    res = g.evaluate(GuardRequest("use_session", P.BROWSER_READ, uses_credential=True,
                                  domain="example.com"))
    assert res.decision == Decision.REQUIRES_APPROVAL


def test_irreversible_requires_approval():
    g = guard()
    res = g.evaluate(GuardRequest("del", P.LOW_RISK_WRITE, is_irreversible=True))
    assert res.decision == Decision.REQUIRES_APPROVAL


def test_low_risk_write_policy_toggle():
    off = guard(policy=PermissionPolicy(allow_low_risk_write=False))
    assert off.evaluate(GuardRequest("note", P.LOW_RISK_WRITE)).decision == Decision.REQUIRES_APPROVAL
    on = guard(policy=PermissionPolicy(allow_low_risk_write=True))
    assert on.evaluate(GuardRequest("note", P.LOW_RISK_WRITE)).decision == Decision.AUTO_ALLOW


def test_terminal_read_first_time_then_trusted():
    g = guard()
    assert g.evaluate(GuardRequest("ls", P.TERMINAL_READ, command="ls")).decision == Decision.REQUIRES_APPROVAL
    trusted = guard(policy=PermissionPolicy(trusted_terminal_read=True))
    assert trusted.evaluate(GuardRequest("ls", P.TERMINAL_READ, command="ls")).decision == Decision.AUTO_ALLOW


def test_path_allowlist_denies_escape():
    g = guard()
    res = g.evaluate(GuardRequest("read", P.SAFE_READ, path="/etc/passwd"))
    assert res.decision == Decision.DENY
    assert res.blocked_by == "path_allowlist"


def test_path_traversal_denied():
    g = guard()
    res = g.evaluate(GuardRequest("read", P.SAFE_READ, path="/ws/../etc/passwd"))
    assert res.decision == Decision.DENY


def test_path_within_root_allowed():
    g = guard()
    res = g.evaluate(GuardRequest("read", P.SAFE_READ, path="/ws/sub/file.txt"))
    assert res.decision == Decision.AUTO_ALLOW


def test_domain_allowlist():
    g = guard()
    assert g.evaluate(GuardRequest("o", P.BROWSER_READ, domain="evil.com")).decision == Decision.DENY
    assert g.evaluate(GuardRequest("o", P.BROWSER_READ, domain="sub.example.com")).decision == Decision.AUTO_ALLOW


def test_command_blocklist():
    g = guard()
    res = g.evaluate(GuardRequest("t", P.TERMINAL_READ, command="rm -rf /"))
    assert res.decision == Decision.DENY
    assert res.blocked_by and "blocklist" in res.blocked_by


def test_command_not_in_allowlist_denied():
    g = guard()
    res = g.evaluate(GuardRequest("t", P.TERMINAL_READ, command="curl http://x"))
    assert res.decision == Decision.DENY


def test_emergency_stop_blocks_non_read():
    g = guard(emergency_stop=True)
    assert g.evaluate(GuardRequest("note", P.LOW_RISK_WRITE)).decision == Decision.DENY
    # SAFE_READ still allowed
    assert g.evaluate(GuardRequest("read", P.SAFE_READ)).decision == Decision.AUTO_ALLOW


def test_private_mode_blocks_network():
    g = guard()
    res = g.evaluate(GuardRequest("api", P.NETWORK_ACCESS, private_mode=True))
    assert res.decision == Decision.DENY
    assert res.blocked_by == "private_mode"

"""Phase 2: desktop app allowlist + PowerShell safety gate (pure logic)."""
from __future__ import annotations

from app.desktop.controller import is_powershell_safe, resolve_app


def test_resolve_known_apps():
    assert resolve_app("VS Code") == "code"
    assert resolve_app("vscode") == "code"
    assert resolve_app("PowerShell") == "powershell"


def test_resolve_unknown_app_denied():
    assert resolve_app("some_random_installer.exe") is None
    assert resolve_app("regedit") is None


def test_powershell_safe_allows_readonly():
    ok, reason = is_powershell_safe("Get-Process | Select-Object -First 5")
    assert ok and reason is None


def test_powershell_blocks_destructive():
    for bad in (
        "Remove-Item C:\\data -Recurse",
        "Set-ExecutionPolicy Unrestricted",
        "net user attacker P@ss /add",
        "reg delete HKLM\\Software /f",
        "Stop-Computer",
        "netsh advfirewall set allprofiles state off",
    ):
        ok, reason = is_powershell_safe(bad)
        assert not ok, bad
        assert reason

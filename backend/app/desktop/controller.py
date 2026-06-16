"""Desktop automation (Phase 2, Windows-first).

All desktop actions are DESKTOP_CONTROL and require approval via the Permission
Guard before reaching here. This module adds a second, defense-in-depth layer:
an app allowlist and a PowerShell command gate (no admin/system-changing
commands). The validation helpers are pure and unit-tested; actual launching is
integration-only and platform-dependent.
"""
from __future__ import annotations

import shutil

# Friendly app aliases the user may name -> executable to launch.
DEFAULT_APP_ALLOWLIST: dict[str, str] = {
    "vscode": "code",
    "vs code": "code",
    "code": "code",
    "browser": "chrome",
    "chrome": "chrome",
    "terminal": "powershell",
    "powershell": "powershell",
    "notepad": "notepad",
    "explorer": "explorer",
}

# Patterns never allowed in an approved PowerShell command (defense in depth on
# top of the global command blocklist).
PS_BLOCKED = (
    "remove-item", "rm ", "del ", "format-", "format ", "diskpart",
    "set-executionpolicy", "new-localuser", "net user", "reg delete", "reg add",
    "stop-computer", "restart-computer", "disable-", "set-mppreference",
    "netsh", "bcdedit", "takeown", "icacls", "shutdown", "sc ", "schtasks",
)


def resolve_app(name: str, allowlist: dict[str, str] | None = None) -> str | None:
    """Map a friendly app name to an allowlisted executable, or None if denied."""
    table = allowlist or DEFAULT_APP_ALLOWLIST
    return table.get(name.strip().lower())


def is_powershell_safe(command: str) -> tuple[bool, str | None]:
    """Reject system-changing PowerShell. Returns (ok, reason)."""
    low = command.lower()
    for bad in PS_BLOCKED:
        if bad in low:
            return False, f"blocked pattern: {bad.strip()}"
    return True, None


class DesktopController:
    def __init__(self, app_allowlist: dict[str, str] | None = None) -> None:
        self.app_allowlist = app_allowlist or DEFAULT_APP_ALLOWLIST

    def open_app(self, name: str) -> dict:
        exe = resolve_app(name, self.app_allowlist)
        if not exe:
            return {"ok": False, "error": f"App '{name}' is not in the desktop allowlist."}
        if shutil.which(exe) is None:  # pragma: no cover - host dependent
            return {"ok": False, "error": f"Executable '{exe}' not found on PATH."}
        try:  # pragma: no cover - launches a real process
            import subprocess

            subprocess.Popen([exe])
            return {"ok": True, "launched": exe}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    def run_powershell(self, command: str) -> dict:
        ok, reason = is_powershell_safe(command)
        if not ok:
            return {"ok": False, "error": reason}
        try:  # pragma: no cover - Windows only
            import subprocess

            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command", command],
                capture_output=True, text=True, timeout=30,
            )
            return {"ok": out.returncode == 0, "stdout": out.stdout[:10_000], "rc": out.returncode}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

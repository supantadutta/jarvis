"""Permission levels, risk levels, and the Permission Guard.

This module is intentionally pure (no DB, no LLM, no I/O) so the security core is
fully unit-testable and cannot be influenced by model output. The Permission
Guard is the *only* authority that decides whether a tool call runs
automatically, needs human approval, or is denied outright.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class PermissionLevel(str, Enum):
    """Capability buckets, ordered loosely from least to most dangerous."""

    SAFE_READ = "SAFE_READ"
    LOW_RISK_WRITE = "LOW_RISK_WRITE"
    BROWSER_READ = "BROWSER_READ"
    BROWSER_WRITE = "BROWSER_WRITE"
    DESKTOP_CONTROL = "DESKTOP_CONTROL"
    TERMINAL_READ = "TERMINAL_READ"
    TERMINAL_WRITE = "TERMINAL_WRITE"
    CREDENTIAL_ACCESS = "CREDENTIAL_ACCESS"
    NETWORK_ACCESS = "NETWORK_ACCESS"
    HIGH_RISK = "HIGH_RISK"


class RiskLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Decision(str, Enum):
    AUTO_ALLOW = "auto_allow"
    REQUIRES_APPROVAL = "requires_approval"
    DENY = "deny"


# Permission levels that may NEVER auto-run, regardless of settings. These encode
# the hard rules from the security model (credentials, terminal writes, anything
# irreversible/high-risk).
ALWAYS_APPROVE: frozenset[PermissionLevel] = frozenset(
    {
        PermissionLevel.BROWSER_WRITE,
        PermissionLevel.DESKTOP_CONTROL,
        PermissionLevel.TERMINAL_WRITE,
        PermissionLevel.CREDENTIAL_ACCESS,
        PermissionLevel.HIGH_RISK,
    }
)

# Levels that auto-run by default (read-only / observational).
AUTO_BY_DEFAULT: frozenset[PermissionLevel] = frozenset(
    {
        PermissionLevel.SAFE_READ,
        PermissionLevel.BROWSER_READ,
    }
)


@dataclass(frozen=True)
class PermissionPolicy:
    """User-tunable knobs the guard consults. Hard rules above cannot be relaxed
    by this policy; the policy can only make things *stricter* or enable the few
    opt-in conveniences (low-risk auto-write, terminal-read trust)."""

    allow_low_risk_write: bool = False
    # A first-time terminal-read still needs approval; once trusted it may auto-run.
    trusted_terminal_read: bool = False
    # Network egress allowed at all (PRIVATE_MODE sets this False).
    allow_network: bool = True


@dataclass
class GuardRequest:
    """Everything the guard needs to make a decision about one tool call."""

    tool_name: str
    permission: PermissionLevel
    risk: RiskLevel = RiskLevel.LOW
    # Optional context used by allowlist checks.
    path: str | None = None
    domain: str | None = None
    command: str | None = None
    uses_credential: bool = False
    is_irreversible: bool = False
    # Mode flags.
    private_mode: bool = False
    trusted_workflow: bool = False  # user previously granted "trust this workflow"


@dataclass
class GuardResult:
    decision: Decision
    reason: str
    permission: PermissionLevel
    risk: RiskLevel
    blocked_by: str | None = None  # name of the allow/blocklist that denied it
    metadata: dict = field(default_factory=dict)


class PermissionGuard:
    """Decides AUTO_ALLOW / REQUIRES_APPROVAL / DENY for a tool call.

    Order of evaluation (first match wins for DENY):
      1. Emergency stop  -> deny everything except SAFE_READ.
      2. Allowlist/blocklist violations -> DENY.
      3. PRIVATE_MODE network/credential restrictions.
      4. Hard "always approve" rules.
      5. Default policy per permission level.
    """

    def __init__(
        self,
        policy: PermissionPolicy | None = None,
        *,
        allowed_paths: list[str] | None = None,
        allowed_domains: list[str] | None = None,
        command_allowlist: list[str] | None = None,
        command_blocklist: list[str] | None = None,
        emergency_stop: bool = False,
    ) -> None:
        self.policy = policy or PermissionPolicy()
        self.allowed_paths = allowed_paths or []
        self.allowed_domains = allowed_domains or []
        self.command_allowlist = command_allowlist or []
        self.command_blocklist = command_blocklist or []
        self.emergency_stop = emergency_stop

    # --- allowlist helpers -------------------------------------------------
    def _path_allowed(self, path: str) -> bool:

        # Reject obvious traversal regardless of platform separators.
        if ".." in path.replace("\\", "/").split("/"):
            return False
        if not self.allowed_paths:
            return False
        norm = path.replace("\\", "/")
        for root in self.allowed_paths:
            r = root.replace("\\", "/").rstrip("/")
            if norm == r or norm.startswith(r + "/"):
                return True
        return False

    def _domain_allowed(self, domain: str) -> bool:
        if not self.allowed_domains:
            return False
        d = domain.lower().strip()
        for allowed in self.allowed_domains:
            a = allowed.lower().strip()
            if d == a or d.endswith("." + a):
                return True
        return False

    def _command_ok(self, command: str) -> tuple[bool, str | None]:
        low = command.lower()
        for bad in self.command_blocklist:
            if bad.lower() in low:
                return False, f"command_blocklist:{bad}"
        if self.command_allowlist:
            head = command.strip().split()
            head0 = head[0] if head else ""
            if not any(head0 == a or low.startswith(a.lower()) for a in self.command_allowlist):
                return False, "command_allowlist"
        return True, None

    # --- main decision -----------------------------------------------------
    def evaluate(self, req: GuardRequest) -> GuardResult:
        perm = req.permission

        # 1. Emergency stop: only pure reads survive.
        if self.emergency_stop and perm != PermissionLevel.SAFE_READ:
            return GuardResult(
                Decision.DENY,
                "Emergency stop is engaged; only SAFE_READ is permitted.",
                perm,
                req.risk,
                blocked_by="emergency_stop",
            )

        # 2. Allowlist / blocklist hard checks.
        if req.path is not None and not self._path_allowed(req.path):
            return GuardResult(
                Decision.DENY,
                f"Path '{req.path}' is outside the allowed workspace roots.",
                perm,
                req.risk,
                blocked_by="path_allowlist",
            )
        if req.domain is not None and not self._domain_allowed(req.domain):
            return GuardResult(
                Decision.DENY,
                f"Domain '{req.domain}' is not in the domain allowlist.",
                perm,
                req.risk,
                blocked_by="domain_allowlist",
            )
        if req.command is not None:
            ok, blocked = self._command_ok(req.command)
            if not ok:
                return GuardResult(
                    Decision.DENY,
                    f"Command rejected by {blocked}.",
                    perm,
                    req.risk,
                    blocked_by=blocked,
                )

        # 3. PRIVATE_MODE restrictions.
        if req.private_mode and perm == PermissionLevel.NETWORK_ACCESS:
            return GuardResult(
                Decision.DENY,
                "Network access is disabled in PRIVATE_MODE.",
                perm,
                req.risk,
                blocked_by="private_mode",
            )

        # 4. Hard always-approve rules.
        if (
            perm in ALWAYS_APPROVE
            or req.uses_credential
            or req.is_irreversible
        ):
            return GuardResult(
                Decision.REQUIRES_APPROVAL,
                self._approval_reason(req),
                perm,
                req.risk,
            )

        # 5. Default per-level policy.
        if perm in AUTO_BY_DEFAULT:
            return GuardResult(Decision.AUTO_ALLOW, "Read-only action.", perm, req.risk)

        if perm == PermissionLevel.LOW_RISK_WRITE:
            if self.policy.allow_low_risk_write:
                return GuardResult(
                    Decision.AUTO_ALLOW,
                    "Low-risk write auto-allowed by policy.",
                    perm,
                    req.risk,
                )
            return GuardResult(
                Decision.REQUIRES_APPROVAL,
                "Low-risk write requires approval (auto-write disabled).",
                perm,
                req.risk,
            )

        if perm == PermissionLevel.TERMINAL_READ:
            if self.policy.trusted_terminal_read or req.trusted_workflow:
                return GuardResult(
                    Decision.AUTO_ALLOW,
                    "Trusted read-only terminal command.",
                    perm,
                    req.risk,
                )
            return GuardResult(
                Decision.REQUIRES_APPROVAL,
                "First-time terminal-read requires approval.",
                perm,
                req.risk,
            )

        if perm == PermissionLevel.NETWORK_ACCESS:
            if self.policy.allow_network:
                return GuardResult(
                    Decision.AUTO_ALLOW, "Network access allowed by policy.", perm, req.risk
                )
            return GuardResult(
                Decision.REQUIRES_APPROVAL, "Network access requires approval.", perm, req.risk
            )

        # Unknown / unmapped -> safest default.
        return GuardResult(
            Decision.REQUIRES_APPROVAL,
            "Unclassified action requires approval by default.",
            perm,
            req.risk,
        )

    @staticmethod
    def _approval_reason(req: GuardRequest) -> str:
        if req.uses_credential:
            return "Uses a saved credential/session; approval required every time."
        if req.is_irreversible:
            return "Action is irreversible; explicit approval required."
        return f"{req.permission.value} always requires approval."

"""Credential manager (interface + safe defaults).

Phase 1 ships the interface, masking, and the approval hook. Real backends
(OS keychain via `keyring`, Fernet file vault, encrypted Playwright sessions)
land in Phase 2. The DB only ever stores metadata + a `vault_ref` pointer — never
the secret value. See docs/credential_model.md.
"""
from __future__ import annotations

from dataclasses import dataclass


def mask(secret: str) -> str:
    """Mask a secret for display: keep at most the last 2 chars."""
    if not secret:
        return ""
    if len(secret) <= 4:
        return "****"
    return "****" + secret[-2:]


@dataclass
class CredentialMeta:
    name: str
    platform: str
    kind: str  # password | token | oauth | session
    username: str | None
    vault_ref: str
    scopes: list[str]
    requires_approval: bool = True
    revoked: bool = False


class VaultBackend:
    """Interface for a secret store. Implementations must never log secrets."""

    def get(self, vault_ref: str) -> str | None:  # pragma: no cover - Phase 2
        raise NotImplementedError

    def set(self, vault_ref: str, secret: str) -> None:  # pragma: no cover - Phase 2
        raise NotImplementedError

    def delete(self, vault_ref: str) -> None:  # pragma: no cover - Phase 2
        raise NotImplementedError


class NullVault(VaultBackend):
    """Default in Phase 1: refuses to return secrets, forcing manual setup."""

    def get(self, vault_ref: str) -> str | None:
        return None

    def set(self, vault_ref: str, secret: str) -> None:
        raise RuntimeError("Configure a real vault backend (keychain/Fernet) in Phase 2.")

    def delete(self, vault_ref: str) -> None:
        return None


class CredentialManager:
    def __init__(self, vault: VaultBackend | None = None) -> None:
        self.vault = vault or NullVault()
        self._meta: dict[str, CredentialMeta] = {}

    def register(self, meta: CredentialMeta) -> None:
        self._meta[meta.name] = meta

    def list_public(self) -> list[dict]:
        """Metadata only; username masked, secret never present."""
        return [
            {
                "name": m.name,
                "platform": m.platform,
                "kind": m.kind,
                "username": mask(m.username or ""),
                "scopes": m.scopes,
                "requires_approval": m.requires_approval,
                "revoked": m.revoked,
            }
            for m in self._meta.values()
        ]

    def revoke(self, name: str) -> bool:
        m = self._meta.get(name)
        if not m:
            return False
        m.revoked = True
        return True

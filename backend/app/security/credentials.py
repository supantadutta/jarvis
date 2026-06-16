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


class FernetVault(VaultBackend):
    """Phase 2: symmetric-encrypted file vault (cryptography/Fernet).

    Stores `{vault_ref: token}` where the token is Fernet-encrypted. The key
    should come from the OS keychain or a user passphrase — never committed.
    `cryptography` is imported lazily so importing this module is free.
    """

    def __init__(self, key: bytes | str, store_path: str = "data/memory/vault.json") -> None:
        try:
            from cryptography.fernet import Fernet
        except ImportError as exc:  # noqa: BLE001
            raise RuntimeError("`pip install cryptography` to use FernetVault.") from exc
        self._fernet = Fernet(key if isinstance(key, bytes) else key.encode())
        self.store_path = store_path
        self._cache: dict[str, str] = self._load()

    @staticmethod
    def generate_key() -> str:
        from cryptography.fernet import Fernet

        return Fernet.generate_key().decode()

    def _load(self) -> dict[str, str]:
        import json
        from pathlib import Path

        p = Path(self.store_path)
        if p.exists():
            try:
                return json.loads(p.read_text())
            except (OSError, ValueError):
                return {}
        return {}

    def _persist(self) -> None:
        import json
        from pathlib import Path

        p = Path(self.store_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self._cache))

    def get(self, vault_ref: str) -> str | None:
        token = self._cache.get(vault_ref)
        if token is None:
            return None
        return self._fernet.decrypt(token.encode()).decode()

    def set(self, vault_ref: str, secret: str) -> None:
        self._cache[vault_ref] = self._fernet.encrypt(secret.encode()).decode()
        self._persist()

    def delete(self, vault_ref: str) -> None:
        self._cache.pop(vault_ref, None)
        self._persist()


class KeyringVault(VaultBackend):
    """Phase 2: OS keychain backend (Windows Credential Manager / macOS Keychain
    / Linux Secret Service) via the `keyring` package."""

    SERVICE = "jarvis"

    def __init__(self) -> None:
        try:
            import keyring  # noqa: F401
        except ImportError as exc:  # noqa: BLE001
            raise RuntimeError("`pip install keyring` to use KeyringVault.") from exc

    def get(self, vault_ref: str) -> str | None:  # pragma: no cover - OS dependent
        import keyring

        return keyring.get_password(self.SERVICE, vault_ref)

    def set(self, vault_ref: str, secret: str) -> None:  # pragma: no cover - OS dependent
        import keyring

        keyring.set_password(self.SERVICE, vault_ref, secret)

    def delete(self, vault_ref: str) -> None:  # pragma: no cover - OS dependent
        import keyring

        try:
            keyring.delete_password(self.SERVICE, vault_ref)
        except Exception:  # noqa: BLE001
            pass


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

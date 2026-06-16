"""Phase 2: browser domain allowlist + credential vault backends."""
from __future__ import annotations

import pytest

from app.browser.controller import BrowserController, domain_of, is_domain_allowed
from app.security.credentials import CredentialManager, CredentialMeta, mask


# --- browser domain allowlist (pure) ---
def test_domain_of_strips_scheme_port_userinfo():
    assert domain_of("https://user:pw@Sub.Example.com:8443/path") == "sub.example.com"
    assert domain_of("example.com/x") == "example.com"


def test_is_domain_allowed_exact_and_subdomain():
    allow = ["example.com"]
    assert is_domain_allowed("https://example.com", allow)
    assert is_domain_allowed("https://app.example.com/x", allow)
    assert not is_domain_allowed("https://evil.com", allow)
    assert not is_domain_allowed("https://notexample.com", allow)
    assert not is_domain_allowed("https://example.com", [])


@pytest.mark.asyncio
async def test_browser_get_text_blocks_disallowed_domain():
    bc = BrowserController(allowed_domains=["example.com"])
    res = await bc.get_text("https://evil.com/login", domain="evil.com")
    assert not res.ok
    assert "allowlist" in (res.error or "")


# --- credential masking + manager (no secrets stored in metadata) ---
def test_mask_hides_secret():
    assert mask("supersecretvalue").endswith("ue")
    assert mask("supersecretvalue").startswith("****")
    assert mask("ab") == "****"


def test_credential_manager_lists_metadata_only():
    cm = CredentialManager()
    cm.register(CredentialMeta(
        name="splunk", platform="splunk", kind="token",
        username="analyst@corp", vault_ref="ref-1", scopes=["read"],
    ))
    pub = cm.list_public()[0]
    assert pub["name"] == "splunk"
    assert "@corp" not in pub["username"]  # masked
    assert "vault_ref" not in pub  # pointer never exposed
    assert cm.revoke("splunk") is True
    assert cm.list_public()[0]["revoked"] is True


def test_fernet_vault_roundtrip_if_available():
    pytest.importorskip("cryptography")  # skip if not installed
    from app.security.credentials import FernetVault

    key = FernetVault.generate_key()
    import tempfile, os

    path = os.path.join(tempfile.mkdtemp(), "vault.json")
    v = FernetVault(key, store_path=path)
    v.set("ref-1", "hunter2")
    assert v.get("ref-1") == "hunter2"
    # encrypted at rest: plaintext secret must not appear in the file
    with open(path) as fh:
        assert "hunter2" not in fh.read()
    v.delete("ref-1")
    assert v.get("ref-1") is None

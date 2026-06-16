# Roadmap

## Phase 1 — MVP (this release) ✅

Core brain + safety, local-first, runs with no paid API.

- FastAPI backend, config, SQLite/Postgres via SQLModel.
- Model registry (+ seed models), capability tags, health check.
- Provider abstraction: **Mock** (tests) + **Ollama** (local default); cloud
  providers scaffolded.
- Model Router (pure, tested) + execution modes.
- Agents: Supervisor, Planner, Verifier (+ base for the rest).
- Tool registry (typed) + built-in tools: read_file, write_note,
  list_directory, search_files, take_desktop_screenshot, open_url_readonly,
  add_memory, search_memory, create_task, get_task_status, request_user_approval,
  create_report_markdown, verify_final_answer, compare_ai_outputs, …
- Permission system + Permission Guard + Approval Queue + Emergency Stop.
- Audit logs with redaction.
- In-memory RAG/memory (Chroma optional).
- Chat API + WebSocket events; Telegram bot scaffold (allowlist, commands).
- Basic Next.js dashboard pages.
- Docker Compose, `.env.example`, Makefile, scripts.
- **Tests**: permission system, model router, tool registry, approvals (+ more).

## Phase 2 — Multi-cloud + modes + voice + desktop  🚧 in progress

Implemented & tested in this release:
- ✅ **Cloud providers live**: OpenAI/Groq/OpenRouter (OpenAI-compatible) + full
  **Anthropic Messages API** and **Gemini generateContent** wire formats
  (pure builders/parsers unit-tested; network calls lazy).
- ✅ **CASCADE / COST_SAVER escalation**: verifier-gated; the paid hop creates an
  approval and waits (tested with the mock provider).
- ✅ **SPECIALIST_TEAM** fan-out across specialist agents (tested).
- ✅ **Browser controller** (Playwright, lazy): domain allowlist + URL helpers
  unit-tested; untrusted-content wrapping on page text.
- ✅ **Credential vaults**: `FernetVault` (encrypted-at-rest, round-trip tested)
  and `KeyringVault` (OS keychain); metadata stays separate from secrets.
- ✅ **Desktop controller** (Windows-first): app allowlist + PowerShell safety
  gate (pure validation unit-tested).
- ✅ **Voice engines** scaffolded: faster-whisper STT + Piper TTS (lazy).

Also implemented:
- ✅ **Health-aware routing**: the router now selects over the *healthy* enabled
  model set (`registry.available()` with a TTL health cache), falling back to the
  enabled set when no health info exists.
- ✅ **Workflow execution engine**: runs a workflow's steps through the assigned
  agents and writes output through the permissioned tool layer; runs are
  recorded and exposed at `POST /workflows/{key}/run` + `GET /workflows/runs`
  (with a Run button on the dashboard). `WorkflowScheduler` lists schedule-trigger
  workflows (cron execution swaps in Arq/APScheduler in production).
- ✅ **Persistence repository**: `persist_task/approval/audit/chat` + loaders map
  the in-memory runtime objects onto the SQLModel tables (tested on SQLite).

Also implemented:
- ✅ **Write-through persistence** (opt-in): the live Brain persists tasks,
  audit entries, approvals, and chat messages to the DB as they happen, via
  listener hooks on the audit log + approval queue (tests stay hermetic with
  persistence off).
- ✅ **SSE streaming** chat endpoint `POST /chat/stream` — emits
  classified → routed → plan → token… → done events; dashboard chat consumes it
  live (toggleable).
- ✅ **Encrypted browser sessions**: `SessionStore` saves Playwright
  `storage_state` encrypted at rest through the vault (DB holds only a pointer);
  round-trip tested.

Also implemented (Phase 2 now feature-complete for the local-first scope):
- ✅ **Provider token streaming**: `stream()` on Mock/Ollama/OpenAI-compatible +
  a `stream_text()` helper; the orchestrator's `stream_answer()` streams the
  worker model's tokens natively for single-model modes (richer modes chunk the
  orchestrated result). Wired into `POST /chat/stream` and the dashboard.
- ✅ **Cron-driven scheduler**: a pure 5-field cron matcher + `WorkflowScheduler`
  with `due()`/`run_due()` (deduped per minute) and an in-process asyncio loop
  (started when `SCHEDULER_ENABLED=true`). Endpoints `GET /scheduler/due` and
  `POST /scheduler/tick`.
- ✅ **Voice command loop**: `POST /voice/command` routes a transcript through the
  orchestrator (approvals still enforced); `GET /voice/status` reports STT
  availability. Audio STT/TTS engines remain lazy (faster-whisper/Piper).

Deferred to Phase 3+ (needs live infra to verify meaningfully):
- Distributed background execution via **Redis/Arq** (current scheduler is
  in-process).
- Full audio capture → STT → TTS round-trip and wake-word.

## Phase 3 — Integrations  🚧 in progress

Implemented & tested in this release:
- ✅ **Document generation**: Markdown (always) + **DOCX / PDF / XLSX** via lazy
  python-docx / reportlab / openpyxl; wired into `create_docx_report`,
  `create_pdf_report`, `create_xlsx_report` tools and `POST /documents/generate`.
- ✅ **SOC / cybersecurity modules** (defensive): Windows Event ID explainer,
  MITRE ATT&CK mapping, Splunk SPL + CrowdStrike LogScale + Sigma builders, IR
  report skeleton; endpoints under `/soc/*`. See `soc_modules.md`.
- ✅ **GitHub automation**: pure README/scaffold generator (`/integrations/readme`)
  + approval-gated REST client scaffold.
- ✅ **Email / calendar**: draft composer (drafts only; sending is HIGH_RISK +
  approval) and RFC-5545 **ICS** event builder (`/integrations/email/draft`).
- ✅ **WhatsApp Cloud API** (official only): message/template payload builders +
  approval-gated `WhatsAppCloudClient` (no unofficial scraping).
- ✅ **n8n**: webhook payload builder + `N8nClient` trigger scaffold.

Remaining for Phase 3 completion:
- Live OAuth for email/calendar providers (Gmail/Graph) behind the credential vault.
- Inbound WhatsApp webhook handler (treating message bodies as untrusted data).
- GitHub write operations (create repo / push / PR) end-to-end behind approval.

## Phase 4 — Advanced

- Wake word. Home Assistant. MCP adapter. Plugin system.
- Advanced self-evaluation. Workflow marketplace. Fine-tuning dataset export.

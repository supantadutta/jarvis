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

Remaining for Phase 2 completion:
- Live streaming responses; wire model health into the router availability filter.
- Persistent Playwright `storage_state` sessions + encrypted at rest.
- Move in-memory runtime stores (tasks/approvals/audit/memory) onto SQLModel +
  Redis/Arq for background tasks and workflow scheduling.
- End-to-end voice push-to-talk loop with voice confirmation on risky actions.

## Phase 3 — Integrations

- WhatsApp Cloud API (official only). n8n integration.
- Email/calendar. DOCX/PDF/XLSX generation. GitHub automation.
- SOC/cybersecurity assistant modules (defensive).

## Phase 4 — Advanced

- Wake word. Home Assistant. MCP adapter. Plugin system.
- Advanced self-evaluation. Workflow marketplace. Fine-tuning dataset export.

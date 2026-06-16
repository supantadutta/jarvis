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

## Phase 2 — Multi-cloud + modes + voice + desktop

- OpenAI / Claude / Gemini / Groq / OpenRouter providers (live).
- Parallel comparison, debate mode, deep-work mode, cost-saver, private mode.
- Voice: faster-whisper STT + Piper TTS (push-to-talk).
- Browser persistent sessions (Playwright `storage_state`).
- Credential vault backends (keychain + Fernet) + session encryption.
- Desktop automation (Windows-first).

## Phase 3 — Integrations

- WhatsApp Cloud API (official only). n8n integration.
- Email/calendar. DOCX/PDF/XLSX generation. GitHub automation.
- SOC/cybersecurity assistant modules (defensive).

## Phase 4 — Advanced

- Wake word. Home Assistant. MCP adapter. Plugin system.
- Advanced self-evaluation. Workflow marketplace. Fine-tuning dataset export.

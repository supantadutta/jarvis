# Database Schema

Defined as SQLModel tables in `backend/app/models/tables.py` and created on
startup via `init_db()`. Default engine is **SQLite** (`data/jarvis.db`); set
`DATABASE_URL` to a Postgres DSN for scale-up. **25 tables**:

| Table | Holds |
|-------|-------|
| `users` | owner account(s) |
| `settings` | key/value app settings |
| `model_providers` | provider rows (local/cloud, base_url, enabled) |
| `models` | model registry rows + capability tags |
| `agents` | agent registry (key, display, default task type) |
| `agent_runs` | per-agent execution records |
| `chat_messages` | chat history (dashboard/telegram/voice) |
| `tasks` | tasks (command, type, mode, status, result) |
| `task_steps` | plan steps with permission/risk/approval |
| `approvals` | approval queue items + decisions |
| `tools` | tool registry snapshot |
| `tool_calls` | every tool invocation + decision |
| `audit_logs` | append-only redacted audit trail |
| `credentials_metadata` | credential **metadata + vault_ref** (never secrets) |
| `browser_profiles` | persistent browser sessions (encrypted storage_state ref) |
| `documents` | indexed documents |
| `memory_chunks` | RAG chunks (collection, text, source, meta) |
| `workflows` | reusable workflow definitions |
| `workflow_runs` | workflow executions |
| `telegram_users` | allowlisted Telegram users |
| `voice_sessions` | transcripts/metadata |
| `screenshots` | desktop/browser screenshot evidence |
| `files_index` | local file index (path, size, mtime, hash) |
| `model_evaluations` | per-(model, task) success rate for router learning |
| `ai_comparisons` | parallel/debate candidate sets + winner |

**Phase 1 runtime note:** for hermetic tests and zero-dependency startup, the
runtime stores for tasks/approvals/audit/memory are in-memory services with the
same shape as these tables; Phase 2 moves the runtime onto the DB rows.

# API Endpoints

All under `/api`. Interactive docs at `/docs` (Swagger) when the backend runs.

| Method | Path | Purpose |
|--------|------|---------|
| GET    | `/health` | System status, model/tool/agent counts, e-stop, pending approvals |
| POST   | `/chat` | Run a command through the orchestrator (`{message, mode?, source?}`) |
| GET    | `/tasks` | Recent tasks |
| GET    | `/tasks/{id}` | Task detail (steps, plan, models, agents) |
| GET    | `/models` | Model registry (capability tags) |
| POST   | `/models/{provider}/{model}/toggle` | Enable/disable a model |
| GET    | `/models/health` | Per-model provider health |
| GET    | `/agents` | Agent registry (roles, permissions, personas) |
| GET    | `/tools` | Tool registry (permission, risk, approval, schema) |
| GET    | `/approvals` · `/approvals/pending` | Approval queue |
| POST   | `/approvals/{id}/decision` | Approve/deny/trust (`{approved, trust?, note?}`) |
| POST   | `/memory/add` · `/memory/search` · GET `/memory/stats` | Local RAG memory |
| GET    | `/audit?limit=N` | Redacted audit log |
| GET    | `/workflows` | Seed workflow definitions |
| POST   | `/control/stop` | Emergency stop (`{engaged: bool}`) |

WebSocket task/agent timelines and Telegram webhooks are wired in Phase 2.

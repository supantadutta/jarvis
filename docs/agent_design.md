# Agent Design

Each agent is a role with: a stable `key`, a system persona, a default
`TaskType` affinity, the permission levels it is *allowed* to request, and the
tools it may use. Agents never escalate their own permissions — the Permission
Guard is the only authority.

| # | Agent           | key             | Responsibility                                                        | May request           |
|---|-----------------|-----------------|-----------------------------------------------------------------------|-----------------------|
| 1 | Supervisor      | `supervisor`    | Classify intent, choose mode, select agents/models, final answer.     | (orchestration only)  |
| 2 | Planner         | `planner`       | Decompose into steps, label risk, choose tools, estimate deps.        | SAFE_READ             |
| 3 | Research        | `research`      | Web research, source checking, summarization, RAG enrichment.         | BROWSER_READ, NETWORK |
| 4 | Code            | `code`          | Write/edit/debug code, scripts, architecture, repo prep.              | LOW_RISK_WRITE        |
| 5 | Browser Auto    | `browser`       | Playwright: open, read, screenshot, (forms/clicks after approval).    | BROWSER_READ/WRITE    |
| 6 | Desktop Auto    | `desktop`       | Open apps, clipboard, move files, screenshots (Windows first).        | DESKTOP_CONTROL       |
| 7 | File & Document | `file`          | Read/organize files, notes, DOCX/PDF/XLSX/MD, summarize, search.      | SAFE_READ, LOW_WRITE  |
| 8 | Credential      | `credential`    | Vault metadata, sessions; never exposes secrets; approval to use.     | CREDENTIAL_ACCESS     |
| 9 | Voice           | `voice`         | STT/TTS, voice confirmation, command routing.                         | SAFE_READ             |
|10 | Telegram        | `telegram`      | Receive commands, progress, approval buttons, files, voice.           | SAFE_READ             |
|11 | Workflow        | `workflow`      | Build/schedule reusable workflows; n8n later.                         | (varies by workflow)  |
|12 | Verifier/Critic | `verifier`      | Quality/safety/completeness check; compare outputs; block unsafe.     | SAFE_READ             |
|13 | SOC / Security  | `soc`           | **Defensive only**: Splunk/LogScale/Wazuh/Suricata queries, Event ID, |                       |
|   |                 |                 | log analysis, IR drafts, MITRE ATT&CK mapping, lab docs.              | SAFE_READ, LOW_WRITE  |

## Agent base contract

```python
class BaseAgent:
    key: str
    display_name: str
    default_task_type: TaskType
    allowed_permissions: set[PermissionLevel]
    system_prompt: str
    async def run(self, ctx: AgentContext) -> AgentResult: ...
```

- `AgentContext` carries the user command, the selected model, conversation +
  retrieved memory, the tool registry handle, and an `approve()` callback.
- `AgentResult` carries the text output, any tool calls made, citations, a
  self-assessed confidence, and the audit records produced.
- Every tool call goes through `ctx.call_tool(name, args)`, which invokes the
  Permission Guard *before* execution. An agent cannot call a tool directly.

## Supervisor responsibilities (Phase 1)

- `classify()` → `(TaskType, Mode)` using cue heuristics + model fallback.
- `select_team()` → list of agent keys appropriate to the task/mode.
- `compose_final()` → merge agent outputs into one answer + verifier verdict.

## SOC agent safety boundary

The SOC agent is constrained at the **prompt + tool** layer to defensive,
educational, lab-authorized output only. It has no offensive tooling: no
exploit execution, malware authoring, credential theft, persistence, evasion,
or stealth. Requests in that direction are declined and logged. See
`threat_model.md`.

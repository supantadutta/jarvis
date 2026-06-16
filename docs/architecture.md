# JARVIS — Architecture Summary

JARVIS is a **local-first multi-AI personal automation platform**. It is not a
single chatbot: it is a supervised team of AI agents that classify a command,
plan it, route each subtask to the best model, execute *approved* actions
through a typed/permissioned tool layer, verify the result, and report back —
over a web dashboard, Telegram, voice, or a desktop command bar.

## Design principles

1. **Local-first / private by default.** The system runs end-to-end on local
   Ollama models with no paid API. Cloud providers are strictly optional and are
   never called in `PRIVATE_MODE`.
2. **Everything risky needs a human.** A central Permission Guard + Approval
   Queue gates every tool call by risk level. The LLM never gets to bypass it.
3. **Untrusted content stays untrusted.** Web pages, emails, files, and external
   messages can never issue commands. Prompt-injection defense is structural,
   not prompt-based.
4. **Auditable.** Every agent run, model call, and tool call is written to an
   append-only audit log with input/output summaries and screenshot references.
5. **Typed contracts.** Models, agents, tools, and tasks all have explicit
   Pydantic schemas. The router and guard operate on data, not free text.

## High-level component map

```
                         ┌──────────────────────────────────────────┐
  Interfaces             │  Web Dashboard   Telegram   Voice   CLI    │
                         └───────────────┬──────────────────────────┘
                                         │ (chat API / webhook)
                         ┌───────────────▼──────────────────────────┐
                         │            FastAPI Backend                │
                         │                                           │
  Brain / orchestration  │   Supervisor → Planner → Router → Agents  │
                         │        │           │         │            │
                         │   Risk Engine   Model      Specialist     │
                         │        │        Registry    Agents        │
                         │   Permission Guard ─────────► Verifier    │
                         └───┬───────────┬──────────┬────────┬───────┘
                             │           │          │        │
                    ┌────────▼──┐  ┌─────▼────┐ ┌───▼────┐ ┌─▼──────┐
  Capabilities      │ Tool      │  │ LLM      │ │ RAG /  │ │ Audit  │
                    │ Registry  │  │ Providers│ │ Memory │ │ Log    │
                    └────┬──────┘  └─────┬────┘ └───┬────┘ └────────┘
                         │               │          │
              ┌──────────┼───────┐  ┌────┴────┐ ┌───┴────┐
              │ files browser    │  │ Ollama  │ │ Chroma │
              │ desktop memory   │  │ OpenAI… │ │ Qdrant │
              └──────────────────┘  └─────────┘ └────────┘
```

## Architecture diagrams (rendered)

> These Mermaid diagrams render automatically on GitHub. They are the canonical
> architectural view; the ASCII map above is a quick text fallback.

### 1. System / component view

```mermaid
flowchart TB
    subgraph UI["🧑 Interfaces"]
        WEB["Web Dashboard<br/>(Next.js)"]
        TG["Telegram Bot<br/>(allowlist)"]
        VOICE["Voice<br/>(push-to-talk · Phase 2)"]
        CLI["Desktop command bar"]
    end

    subgraph API["⚙️ FastAPI Backend  /api/*"]
        ROUTES["Routes<br/>chat · tasks · models · agents<br/>tools · approvals · memory · audit · health"]
    end

    subgraph BRAIN["🧠 Jarvis Brain (composition root)"]
        SUP["Supervisor<br/>classify · pick mode · compose"]
        PLAN["Planner<br/>steps + risk labels"]
        ROUTER["Model Router<br/>filter → score → select"]
        VER["Verifier / Critic"]
        subgraph SPEC["Specialist agents"]
            RES["Research"]; CODE["Code"]; FILE["File/Doc"]
            BRW["Browser"]; DESK["Desktop"]; SOC["SOC (defensive)"]
        end
    end

    subgraph SEC["🔒 Security layer"]
        GUARD["Permission Guard<br/>10 levels · allowlists · e-stop"]
        APPQ["Approval Queue<br/>approve / deny / trust"]
        PI["Prompt-injection defense<br/>+ secret redaction"]
    end

    subgraph CAP["🧰 Capabilities"]
        TOOLS["Tool Registry (29)<br/>+ ToolExecutor"]
        LLM["LLM Providers<br/>Mock · Ollama · OpenAI-compat · Anthropic/Gemini"]
        MEM["RAG / Memory"]
        AUDIT["Audit Log (JSONL)"]
        DB[("SQLModel · 25 tables<br/>SQLite / Postgres")]
    end

    subgraph EXT["🌐 External (optional)"]
        OLL["Ollama (local)"]
        CLOUD["OpenAI · Claude · Gemini · Groq · OpenRouter"]
        BROWSER["Playwright"]
        VEC["Chroma / Qdrant"]
    end

    UI --> ROUTES --> SUP
    SUP --> PLAN --> ROUTER --> SPEC
    SUP --> ROUTER
    SPEC --> VER --> SUP
    ROUTER -. selects .-> LLM

    SPEC -->|every tool call| TOOLS
    TOOLS --> GUARD
    GUARD -->|requires approval| APPQ
    APPQ -. resolved by .-> UI
    GUARD -->|auto-allow| EXTRUN["run tool"]
    TOOLS --> AUDIT
    PI -. wraps untrusted content .-> SPEC

    LLM --> OLL
    LLM --> CLOUD
    TOOLS --> BROWSER
    MEM --> VEC
    SUP --> MEM
    ROUTES --> DB
    AUDIT --> DB

    classDef sec fill:#3a1f1f,stroke:#c0392b,color:#fff;
    classDef brain fill:#1f2d3a,stroke:#2980b9,color:#fff;
    class GUARD,APPQ,PI sec;
    class SUP,PLAN,ROUTER,VER brain;
```

### 2. Request lifecycle (non-trivial task)

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Sup as Supervisor
    participant Router as Model Router
    participant Plan as Planner
    participant Agent as Specialist Agent
    participant Guard as Permission Guard
    participant Appr as Approval Queue
    participant Ver as Verifier
    participant Audit as Audit Log

    User->>Sup: command (chat / Telegram / voice)
    Sup->>Sup: classify intent → (TaskType, Mode)
    Sup->>Router: route(task, mode, privacy, needs…)
    Router-->>Sup: selected model(s)
    Sup->>Plan: decompose into steps
    Plan-->>Sup: steps + risk labels
    loop each step
        Sup->>Agent: execute step (with chosen model)
        Agent->>Guard: call_tool(name, args)
        alt auto-allow (SAFE_READ / BROWSER_READ)
            Guard-->>Agent: run tool
        else requires approval
            Guard->>Appr: create approval (preview, risk, what-changes)
            Appr-->>User: approve / deny / trust?
            User-->>Appr: decision
            Appr-->>Agent: granted → run · denied → abort
        else deny (allowlist / e-stop)
            Guard-->>Agent: blocked
        end
        Agent->>Audit: record(input, output, risk, approval)
    end
    Sup->>Ver: verify final output (deep/verifier/debate)
    Ver-->>Sup: passed? score, issues
    Sup-->>User: composed final answer
    Sup->>Audit: record task summary
```

### 3. Model-router decision flow

```mermaid
flowchart TD
    A["RoutingRequest<br/>task · mode · privacy · reasoning<br/>coding · speed · cost · context · tools"] --> B{Availability<br/>enabled & healthy?}
    B -- no --> X[(reject)]
    B -- yes --> C{Hard constraints}
    C -->|PRIVATE / free-only → drop paid| X
    C -->|privacy &lt; required| X
    C -->|context &lt; needed| X
    C -->|needs tools/vision unmet| X
    C -- pass --> D["Score<br/>w·reasoning + w·coding* + w·speed<br/>+ w·privacy + w·task-affinity<br/>− cost-penalty + perf-history"]
    D --> E{Mode?}
    E -->|single / fast / private| F["Top 1"]
    E -->|parallel / debate / deep| G["Top k<br/>+ provider diversity"]
    E -->|cascade / cost-saver| H["Ordered list<br/>local/cheap first"]
    F --> R[[RoutingResult]]
    G --> R
    H --> R
```

### 4. Execution modes at a glance

```mermaid
flowchart LR
    CMD([User command]) --> M{Detected mode}
    M -->|fast| F["1 small local model<br/>skip planning"]
    M -->|single best| S["1 best model"]
    M -->|verifier| V["worker → critic"]
    M -->|parallel| P["N models → compare"]
    M -->|debate| D["N propose → judge picks"]
    M -->|deep work| W["planner + ≥2 models<br/>+ verifier → save to memory"]
    M -->|private| PR["local only<br/>cloud & net blocked"]
    M -->|cost saver| C["local first<br/>cloud on approval"]
    F & S & V & P & D & W & PR & C --> OUT([Final answer + audit])
```


## Request lifecycle (non-trivial task)

1. User sends a command (dashboard / Telegram / voice).
2. **Supervisor** classifies intent → `TaskType` + execution `Mode`.
3. **Model Router** selects the best model (or team) given task, privacy, mode,
   reasoning/coding/speed needs, context length, tool support, availability.
4. **Planner** decomposes the task into ordered `TaskStep`s.
5. **Risk Engine** labels every step with a `PermissionLevel` + `RiskLevel`.
6. **Permission Guard** decides: auto-run, run-if-enabled, or require approval.
7. Specialist agents execute auto-approved steps via the **Tool Registry**.
8. Risky steps create an **Approval** and pause until the human approves/denies.
9. **Verifier** checks the final output for correctness, safety, completeness.
10. **Supervisor** composes the final answer.
11. **Audit log** persists every step, model call, and tool call.

## Local-first stack

| Concern        | Default (local)        | Optional / scale-up           |
|----------------|------------------------|-------------------------------|
| LLM            | Ollama                 | OpenAI/Claude/Gemini/Groq/OR  |
| DB             | SQLite (`jarvis.db`)   | PostgreSQL                    |
| Queue          | in-process async       | Redis + Arq/Celery            |
| Vector memory  | in-memory / Chroma     | Qdrant                        |
| Browser        | Playwright (headed)    | headless / persistent profile |

The MVP runs with **only Python + SQLite + a mock or Ollama provider** — no
external service is required to start, develop, or run the test suite.

See the companion docs: `multi_ai_design.md`, `model_router.md`,
`agent_design.md`, `security_model.md`, `credential_model.md`, `threat_model.md`,
`browser_automation.md`, `workflow_automation.md`, `telegram_setup.md`,
`voice_setup.md`, `roadmap.md`.

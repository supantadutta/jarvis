# Multi-AI Design

JARVIS coordinates multiple models and multiple agents under one supervisor.
Two orthogonal concepts:

- **Agents** = roles with responsibilities and a system persona (Supervisor,
  Planner, Verifier, Research, Code, …). An agent is *who* does the work.
- **Models** = the underlying LLMs (ollama/llama, anthropic/claude, …). A model
  is *what brain* an agent uses for a given step. The Model Router binds an
  agent step to a concrete model.

## Execution modes

| Mode                | What it does                                                        | Cloud? |
|---------------------|--------------------------------------------------------------------|--------|
| `SINGLE_BEST_MODEL` | Router picks one best model and runs it.                           | maybe  |
| `CASCADE_MODE`      | Local model first; escalate to stronger model if weak/approved.   | on esc |
| `PARALLEL_MODE`     | Same task to N models; outputs compared.                          | maybe  |
| `SPECIALIST_TEAM`   | Work split across specialist agents.                              | maybe  |
| `DEBATE_MODE`       | N models propose; a judge/verifier picks the best.               | maybe  |
| `VERIFIER_MODE`     | One model executes; a second reviews accuracy/safety.            | maybe  |
| `FAST_MODE`         | Smallest capable local model; skip debate.                       | no     |
| `DEEP_WORK_MODE`    | Planner + ≥2 specialists + verifier + optional parallel/compare. | maybe  |
| `PRIVATE_MODE`      | Local models + local tools only. No cloud. Web disabled.         | never  |
| `COST_SAVER_MODE`   | Local first; cloud only after explicit approval.                 | on appr|

### Mode selection heuristics

The Supervisor maps natural-language cues to modes before routing:

- "fast" / "quick" / "do it now" → `FAST_MODE`
- "deep work" / "world-class" / "best possible" / "maximum accuracy" /
  "use multiple AI" → `DEEP_WORK_MODE`
- "private" / "local only" → `PRIVATE_MODE`
- "compare X and Y" → `PARALLEL_MODE`
- "save cost" / "cheap" → `COST_SAVER_MODE`
- otherwise → `SINGLE_BEST_MODEL`

`PRIVATE_MODE` is a hard constraint: it strips all non-local models from the
candidate set *before* routing, so a cloud model can never be chosen even if it
would score higher.

## Agent collaboration patterns

```
SINGLE_BEST     user → supervisor → [model] → verifier? → answer
CASCADE         user → local → (weak?) → cloud → answer
PARALLEL        user → {m1,m2,m3} → compare → answer
SPECIALIST_TEAM supervisor → planner → {research, code, file} → supervisor
DEBATE          {m1,m2,m3} propose → judge(verifier) → answer
VERIFIER        worker → verifier(approve/revise) → answer
DEEP_WORK       planner → team → parallel(optional) → compare → verifier → answer
```

## Consensus / debate scoring

When multiple outputs exist (`PARALLEL`, `DEBATE`), a Verifier model scores each
candidate on: correctness, completeness, safety, and grounding. The highest
composite score wins; ties break toward the more privacy-preserving / cheaper
model. The full comparison is stored in `ai_comparisons` for transparency.

## Why a mock provider

For tests and offline development a `MockProvider` returns deterministic,
inspectable responses. The whole orchestration graph (router, agents, verifier,
debate, cascade) is exercised without any network call — this keeps the test
suite hermetic and the project usable with zero API keys.

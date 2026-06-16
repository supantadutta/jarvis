# Model Router Design

The Model Router selects the best model(s) for a step. It is **pure, typed, and
deterministic** so it can be unit-tested without any LLM.

## Inputs

```
RoutingRequest:
  task_type:        TaskType          # coding, research, cybersecurity, ...
  mode:             Mode              # PRIVATE_MODE, DEEP_WORK_MODE, ...
  privacy_required: PrivacyLevel      # min privacy the data demands
  min_reasoning:    int (0-5)
  min_coding:       int (0-5)
  speed_priority:   int (0-5)         # higher = prefer faster
  cost_setting:     CostSetting       # free_only | prefer_local | allow_paid
  min_context:      int               # tokens the prompt needs
  needs_tools:      bool              # requires tool/function calling
  needs_vision:     bool
```

## Algorithm

1. **Availability filter** — drop models that are `enabled=False` or whose
   provider health check is failing.
2. **Hard-constraint filter** — drop models that violate any hard requirement:
   - `PRIVATE_MODE` or `cost_setting=free_only` → keep only local/free models.
   - `privacy_level < privacy_required` → drop.
   - `max_context < min_context` → drop.
   - `needs_tools` and not `tool_calling_support` → drop.
   - `needs_vision` and not `vision_support` → drop.
3. **Scoring** — score each surviving candidate:

   ```
   score =  w_reason * reasoning_level
          + w_code   * coding_level        (only if task is code-ish)
          + w_speed  * speed_level * speed_priority_norm
          + w_privacy* privacy_level
          + w_task   * task_affinity(model, task_type)
          - w_cost   * cost_penalty(cost_type, cost_setting)
          + w_perf   * historical_success_rate(model, task_type)
   ```

   Weights are tuned per mode (e.g. `DEEP_WORK_MODE` up-weights reasoning;
   `FAST_MODE` up-weights speed and forces local).

4. **Tie-break** — prefer (a) higher privacy, (b) lower cost, (c) higher
   `fallback_priority`.
5. **Selection by mode**:
   - single-model modes → top 1.
   - `PARALLEL`/`DEBATE`/`DEEP_WORK` → top *k* (default 3) with provider
     diversity (don't pick three of the same provider if alternatives exist).
   - `CASCADE`/`COST_SAVER` → ordered list, cheapest/local first.

## Capability tags (per model)

`privacy_level, speed_level, reasoning_level, coding_level` are integers 0–5.
`cost_type ∈ {local, free, paid}`. `task_affinity` is a small table mapping a
model's declared strengths to `TaskType`s (e.g. `deepseek-coder` → `coding`).

## Historical performance

`model_evaluations` records per-(model, task_type) success/quality so the router
can learn. In Phase 1 this is a stored average that nudges the score; it never
overrides a hard constraint.

## Fallback / cascade

`route_cascade()` returns the candidates ordered local→cloud. The executor tries
each in order, escalating only when (a) the previous output fails the Verifier's
quality bar **and** (b) the mode/cost-setting permits escalation (with approval
in `COST_SAVER_MODE`).

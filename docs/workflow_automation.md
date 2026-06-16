# Workflow Automation

Workflows are **reusable, named automations** with an explicit risk/approval
policy and an optional schedule. They are stored in `workflows` and each
execution in `workflow_runs`.

## Workflow definition

```yaml
key: morning_briefing
name: Morning Briefing
trigger: schedule            # schedule | manual | event
schedule: "0 7 * * *"        # cron (local time)
required_agents: [research, file, verifier]
required_tools: [search_memory, open_url_readonly, create_report_markdown]
risk_level: low
approval_policy: auto_safe   # auto_safe | approve_each | trusted
output_location: data/notes/briefings
rollback: none               # describe rollback if the workflow writes/changes
steps:
  - agent: research
    action: gather top items from allowlisted sources
  - agent: file
    action: create_report_markdown(briefing)
  - agent: verifier
    action: verify_final_answer
```

## Seeded workflows (definitions in Phase 1, execution maturing through phases)

- **Morning briefing** — summarize agenda/news from allowlisted sources.
- **Check email & draft replies** — drafts only; sending needs HIGH_RISK approval.
- **Download daily report** — browser session + `BROWSER_WRITE` approval.
- **Organize Downloads folder** — `organize_folder` (LOW_RISK_WRITE, in-workspace).
- **Create SOC report** — SOC agent drafts a defensive shift summary.
- **Generate GitHub README** — Code/File agents produce a README.
- **Backup selected folders** — copy (never delete) to a backup root.
- **Summarize new PDFs** — index + summarize new files in a watched folder.
- **Daily study plan** — planner + file agents produce a plan note.

## Each workflow records

trigger · steps · required agents · required tools · risk level · approval
policy · schedule · output location · rollback plan.

## Scheduling

Phase 1: definitions + manual run endpoint. Phase 2+: scheduler (Arq/APScheduler)
fires `schedule` triggers; trusted low-risk steps auto-run, risky steps still
create approvals. n8n integration is Phase 3.

"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function WorkflowsPage() {
  const [wf, setWf] = useState<any[]>([]);
  useEffect(() => { api.workflows().then((d) => setWf(d.workflows)).catch(() => {}); }, []);
  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold mb-4">Workflows</h1>
      <div className="space-y-3">
        {wf.map((w) => (
          <div key={w.key} className="rounded border border-neutral-800 p-4">
            <div className="font-semibold">{w.name} <span className="text-xs text-neutral-500">({w.key})</span></div>
            <div className="text-sm text-neutral-400">trigger={w.trigger} {w.schedule && `· cron=${w.schedule}`} · risk={w.risk_level} · policy={w.approval_policy}</div>
            <div className="text-xs text-neutral-500 mt-1">agents: {w.required_agents.join(", ")} · tools: {w.required_tools.join(", ")}</div>
            <ol className="mt-2 text-sm list-decimal ml-5 text-neutral-300">{w.steps.map((s: string, i: number) => <li key={i}>{s}</li>)}</ol>
          </div>
        ))}
      </div>
    </div>
  );
}

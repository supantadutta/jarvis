"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function WorkflowsPage() {
  const [wf, setWf] = useState<any[]>([]);
  const [runs, setRuns] = useState<any[]>([]);
  const [busy, setBusy] = useState("");

  async function loadRuns() {
    try { setRuns((await api.workflowRuns()).runs); } catch {}
  }
  useEffect(() => {
    api.workflows().then((d) => setWf(d.workflows)).catch(() => {});
    loadRuns();
  }, []);

  async function run(key: string) {
    setBusy(key);
    try { await api.runWorkflow(key); await loadRuns(); } catch {}
    setBusy("");
  }

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold mb-4">Workflows</h1>
      <div className="space-y-3">
        {wf.map((w) => (
          <div key={w.key} className="rounded border border-neutral-800 p-4">
            <div className="flex justify-between items-start">
              <div>
                <div className="font-semibold">{w.name} <span className="text-xs text-neutral-500">({w.key})</span></div>
                <div className="text-sm text-neutral-400">trigger={w.trigger} {w.schedule && `· cron=${w.schedule}`} · risk={w.risk_level} · policy={w.approval_policy}</div>
                <div className="text-xs text-neutral-500 mt-1">agents: {w.required_agents.join(", ")} · tools: {w.required_tools.join(", ")}</div>
              </div>
              <button onClick={() => run(w.key)} disabled={busy === w.key}
                className="rounded bg-blue-600 px-3 py-1 text-sm disabled:opacity-50">
                {busy === w.key ? "…" : "Run"}
              </button>
            </div>
            <ol className="mt-2 text-sm list-decimal ml-5 text-neutral-300">{w.steps.map((s: string, i: number) => <li key={i}>{s}</li>)}</ol>
          </div>
        ))}
      </div>

      <h2 className="text-xl font-bold mt-8 mb-3">Recent runs</h2>
      {runs.length === 0 && <p className="text-neutral-500">No runs yet.</p>}
      <div className="space-y-2">
        {runs.map((r) => (
          <div key={r.id} className="rounded border border-neutral-800 p-3 text-sm">
            <div className="flex justify-between">
              <span className="font-mono">{r.workflow_key}</span>
              <span className={r.status === "completed" ? "text-green-400" : r.status === "failed" ? "text-red-400" : ""}>{r.status}</span>
            </div>
            {r.outputs?.length > 0 && <div className="text-xs text-neutral-500">output: {r.outputs.join(", ")}</div>}
            {r.error && <div className="text-xs text-red-400">{r.error}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}

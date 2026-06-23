"use client";
import { useState } from "react";
import { api } from "@/lib/api";

export default function AgentPage() {
  const [goal, setGoal] = useState("Research the latest on local LLMs and save a markdown note.");
  const [steps, setSteps] = useState(8);
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true); setRes(null);
    try { setRes(await api.agentRun(goal, steps)); }
    catch (e: any) { setRes({ error: String(e) }); }
    setBusy(false);
  }

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold mb-1">Autonomous Agent</h1>
      <p className="text-sm text-neutral-500 mb-4">Give a goal; JARVIS reasons with a connected model and takes guard-gated actions (web, files, memory, reports…) until done. Risky steps create approvals.</p>
      <textarea className="w-full h-24 rounded bg-neutral-900 border border-neutral-700 px-3 py-2"
        value={goal} onChange={(e) => setGoal(e.target.value)} />
      <div className="flex items-center gap-2 mt-2">
        <label className="text-sm text-neutral-400">max steps</label>
        <input type="number" className="w-20 rounded bg-neutral-900 border border-neutral-700 px-2 py-1"
          value={steps} onChange={(e) => setSteps(parseInt(e.target.value) || 8)} />
        <button onClick={run} disabled={busy} className="rounded bg-blue-600 px-4 py-2 disabled:opacity-50">
          {busy ? "Running…" : "Run agent"}
        </button>
      </div>

      {res?.error && <div className="mt-4 text-red-400">{res.error}</div>}
      {res && !res.error && (
        <div className="mt-6">
          <div className="text-sm text-neutral-500 mb-2">model={res.model} · completed={String(res.completed)}
            {res.pending_approvals?.length > 0 && ` · ⚠ approvals: ${res.pending_approvals.join(", ")}`}</div>
          <ol className="space-y-2">
            {res.steps?.map((s: any) => (
              <li key={s.n} className="rounded border border-neutral-800 p-3 text-sm">
                <div className="flex justify-between">
                  <span><b>{s.n}.</b> <code>{s.tool}</code> <span className="text-neutral-500">{JSON.stringify(s.args)}</span></span>
                  <span className={s.decision === "deny" ? "text-red-400" : s.decision === "requires_approval" ? "text-yellow-400" : "text-green-400"}>{s.decision}</span>
                </div>
                {s.thought && <div className="text-xs text-neutral-500 mt-1">💭 {s.thought}</div>}
                <div className="text-xs mt-1">{s.observation}</div>
              </li>
            ))}
          </ol>
          <div className="mt-4 rounded border border-blue-900 bg-neutral-900/50 p-3 whitespace-pre-wrap">{res.answer}</div>
        </div>
      )}
    </div>
  );
}

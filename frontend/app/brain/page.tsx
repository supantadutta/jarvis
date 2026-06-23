"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function BrainPage() {
  const [command, setCommand] = useState("Research the latest local LLMs and write a verified report.");
  const [analysis, setAnalysis] = useState<any>(null);
  const [plan, setPlan] = useState<any>(null);
  const [exec, setExec] = useState<any>(null);
  const [status, setStatus] = useState<any>(null);
  const [bench, setBench] = useState<any>(null);
  const [busy, setBusy] = useState("");

  async function loadStatus() { try { setStatus(await api.brainStatus()); } catch {} }
  useEffect(() => { loadStatus(); }, []);

  async function analyze() { setBusy("a"); try { setAnalysis(await api.brainAnalyze(command)); } catch {} setBusy(""); }
  async function planIt() { setBusy("p"); try { setPlan(await api.brainPlan(command)); } catch {} setBusy(""); }
  async function execute() { setBusy("e"); setExec(null); try { setExec(await api.brainExecute(command)); } catch (e: any) { setExec({ error: String(e) }); } setBusy(""); loadStatus(); }
  async function runBench() { setBusy("b"); try { setBench(await api.brainBenchmarks()); } catch {} setBusy(""); }

  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-bold mb-1">🧠 Cognitive Engine v2</h1>
      <p className="text-sm text-neutral-500 mb-4">Analyze → plan (DAG) → execute as a multi-agent graph. Every tool node passes the Permission Guard.</p>

      <textarea className="w-full h-20 rounded bg-neutral-900 border border-neutral-700 px-3 py-2"
        value={command} onChange={(e) => setCommand(e.target.value)} />
      <div className="flex gap-2 mt-2">
        <button onClick={analyze} disabled={!!busy} className="rounded bg-neutral-700 px-3 py-2 text-sm">Analyze</button>
        <button onClick={planIt} disabled={!!busy} className="rounded bg-neutral-700 px-3 py-2 text-sm">Plan</button>
        <button onClick={execute} disabled={!!busy} className="rounded bg-blue-600 px-4 py-2 text-sm">Execute</button>
        <button onClick={runBench} disabled={!!busy} className="rounded bg-neutral-700 px-3 py-2 text-sm ml-auto">Run benchmarks</button>
      </div>

      {analysis && (
        <div className="mt-4 rounded border border-neutral-800 p-3 text-sm">
          <div className="font-semibold mb-1">Analysis</div>
          <div>type=<b>{analysis.task_type}</b> · risk={analysis.risk_level} · complexity={analysis.complexity} · privacy={analysis.privacy_sensitivity} · cloud_allowed={String(analysis.cloud_allowed)}</div>
          <div className="text-neutral-400">skills: {analysis.required_skills?.join(", ")} · mode: {analysis.suggested_mode} · verifier: {String(analysis.verifier_mandatory)}</div>
        </div>
      )}

      {plan && (
        <div className="mt-4 rounded border border-neutral-800 p-3 text-sm">
          <div className="font-semibold mb-1">Plan (strategy: {plan.strategy})</div>
          <ol className="space-y-1">
            {plan.plan.nodes.map((n: any) => (
              <li key={n.id}><code>{n.id}</code> [{n.kind}/{n.permission}/{n.risk}] {n.description}
                {n.depends_on?.length > 0 && <span className="text-neutral-500"> ⟵ {n.depends_on.join(", ")}</span>}
                {n.approval_required && <span className="text-yellow-400"> ⚠ approval</span>}
              </li>
            ))}
          </ol>
        </div>
      )}

      {exec && !exec.error && (
        <div className="mt-4 rounded border border-blue-900 p-3 text-sm">
          <div className="font-semibold mb-1">Execution graph (completed={String(exec.completed)})</div>
          {exec.nodes?.map((n: any) => (
            <div key={n.node_id} className="flex justify-between border-b border-neutral-800 py-1">
              <span><code>{n.node_id}</code> {n.output?.slice(0, 80)}</span>
              <span className={n.status === "completed" ? "text-green-400" : n.status === "skipped" ? "text-neutral-500" : "text-yellow-400"}>{n.status} {n.latency_ms}ms</span>
            </div>
          ))}
          <div className="mt-2 whitespace-pre-wrap">{exec.final}</div>
        </div>
      )}

      {bench && (
        <div className="mt-4 rounded border border-neutral-800 p-3 text-sm">
          <div className="font-semibold">Benchmarks — overall {bench.overall_score} · passed {String(bench.passed)}</div>
          {bench.suites?.map((s: any) => (
            <div key={s.name} className="flex justify-between"><span>{s.name}</span><span className={s.passed ? "text-green-400" : "text-red-400"}>{s.score} ({s.details})</span></div>
          ))}
        </div>
      )}

      {status && (
        <div className="mt-6 text-xs text-neutral-500">
          CPU {status.resources.cpu_count} · RAM {status.resources.ram_gb}GB · GPU {String(status.resources.gpu)} · max_parallel {status.resources.max_parallel_jobs} · cache hit-rate {status.response_cache.hit_rate} · queue jobs {status.queue.jobs}
        </div>
      )}
    </div>
  );
}

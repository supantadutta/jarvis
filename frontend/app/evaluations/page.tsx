"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function EvaluationsPage() {
  const [rows, setRows] = useState<any[]>([]);
  const [plugins, setPlugins] = useState<any[]>([]);
  useEffect(() => {
    api.evaluations().then((d) => setRows(d.evaluations)).catch(() => {});
    api.plugins().then((d) => setPlugins(d.plugins)).catch(() => {});
  }, []);
  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold mb-4">Model Self-Evaluation</h1>
      <p className="text-sm text-neutral-500 mb-3">Verifier verdicts feed the router so it learns which models do best per task.</p>
      {rows.length === 0 && <p className="text-neutral-500">No evaluations yet — run some deep-work tasks.</p>}
      <table className="w-full text-sm">
        <thead className="text-neutral-400 text-left"><tr><th>Model</th><th>Task</th><th>Samples</th><th>Success</th><th>Avg score</th></tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-neutral-800">
              <td className="py-1">{r.model}</td><td>{r.task_type}</td><td>{r.samples}</td>
              <td>{(r.success_rate * 100).toFixed(0)}%</td><td>{r.avg_score}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2 className="text-xl font-bold mt-8 mb-2">Plugins</h2>
      {plugins.length === 0 && <p className="text-neutral-500">No plugins loaded.</p>}
      {plugins.map((p, i) => (
        <div key={i} className="text-sm border-t border-neutral-800 py-1">
          {p.name} — {p.error ? <span className="text-red-400">{p.error}</span> : `tools: ${p.tools_added?.join(", ")}`}
        </div>
      ))}
    </div>
  );
}

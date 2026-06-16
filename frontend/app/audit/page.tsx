"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function AuditPage() {
  const [entries, setEntries] = useState<any[]>([]);
  async function load() { try { setEntries((await api.audit(200)).entries); } catch {} }
  useEffect(() => { load(); const t = setInterval(load, 4000); return () => clearInterval(t); }, []);
  return (
    <div className="max-w-5xl">
      <h1 className="text-2xl font-bold mb-4">Audit Log</h1>
      <table className="w-full text-xs">
        <thead className="text-neutral-400 text-left"><tr><th>Time</th><th>Agent</th><th>Model</th><th>Tool</th><th>Risk</th><th>Approval</th><th>Output</th></tr></thead>
        <tbody>
          {entries.map((e) => (
            <tr key={e.id} className="border-t border-neutral-800 align-top">
              <td className="py-1 whitespace-nowrap">{e.timestamp?.slice(11, 19)}</td>
              <td>{e.agent}</td><td>{e.model}</td><td>{e.tool}</td><td>{e.risk}</td><td>{e.approval_status}</td>
              <td className="text-neutral-400">{(e.output_summary || e.error || "").slice(0, 80)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

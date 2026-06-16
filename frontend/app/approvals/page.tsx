"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function ApprovalsPage() {
  const [items, setItems] = useState<any[]>([]);
  async function load() {
    try { setItems((await api.approvals()).approvals); } catch {}
  }
  useEffect(() => { load(); const t = setInterval(load, 3000); return () => clearInterval(t); }, []);

  async function decide(id: string, approved: boolean, trust = false) {
    await api.decideApproval(id, approved, trust);
    load();
  }

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold mb-4">Approval Queue</h1>
      {items.length === 0 && <p className="text-neutral-500">No approvals.</p>}
      <div className="space-y-3">
        {items.map((a) => (
          <div key={a.id} className="rounded border border-neutral-800 p-4">
            <div className="flex justify-between">
              <span className="font-mono text-sm">{a.id}</span>
              <span className="text-xs uppercase">{a.status} · risk:{a.risk}</span>
            </div>
            <div className="mt-1 font-semibold">{a.requested_action}</div>
            <div className="text-sm text-neutral-400">
              agent={a.agent} · tool={a.tool} · model={a.model}
            </div>
            <div className="mt-1 text-sm">Preview: <code>{a.action_preview}</code></div>
            <div className="text-sm text-neutral-400">Can change: {a.what_can_change}</div>
            {a.status === "pending" && (
              <div className="mt-3 flex gap-2">
                <button onClick={() => decide(a.id, true)} className="rounded bg-green-700 px-3 py-1 text-sm">Approve once</button>
                <button onClick={() => decide(a.id, false)} className="rounded bg-red-700 px-3 py-1 text-sm">Deny</button>
                {a.allow_trust && (
                  <button onClick={() => decide(a.id, true, true)} className="rounded bg-blue-700 px-3 py-1 text-sm">Trust workflow</button>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

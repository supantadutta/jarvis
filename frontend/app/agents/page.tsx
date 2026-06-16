"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function AgentsPage() {
  const [agents, setAgents] = useState<any[]>([]);
  useEffect(() => { api.agents().then((d) => setAgents(d.agents)).catch(() => {}); }, []);
  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold mb-4">Agents</h1>
      <div className="space-y-3">
        {agents.map((a) => (
          <div key={a.key} className="rounded border border-neutral-800 p-4">
            <div className="font-semibold">{a.display_name} <span className="text-xs text-neutral-500">({a.key})</span></div>
            <div className="text-sm text-neutral-400">task: {a.default_task_type} · perms: {a.allowed_permissions?.join(", ")}</div>
            <p className="text-sm mt-2 text-neutral-300">{a.system_prompt}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

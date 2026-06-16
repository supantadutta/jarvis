"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function TasksPage() {
  const [tasks, setTasks] = useState<any[]>([]);
  async function load() { try { setTasks((await api.tasks()).tasks); } catch {} }
  useEffect(() => { load(); const t = setInterval(load, 3000); return () => clearInterval(t); }, []);
  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold mb-4">Tasks</h1>
      {tasks.length === 0 && <p className="text-neutral-500">No tasks yet.</p>}
      <div className="space-y-3">
        {tasks.map((t) => (
          <div key={t.id} className="rounded border border-neutral-800 p-4">
            <div className="flex justify-between"><span className="font-mono text-sm">{t.id}</span><span className="text-xs">{t.status} · {t.mode}</span></div>
            <div className="mt-1">{t.command}</div>
            <div className="text-xs text-neutral-500 mt-1">type={t.task_type} · models={t.models?.join(", ")} · agents={t.agents?.join(", ")}</div>
            {t.steps?.length > 0 && (
              <ol className="mt-2 text-sm list-decimal ml-5 text-neutral-300">
                {t.steps.map((s: any) => <li key={s.index}>[{s.permission}/{s.risk}] {s.description}</li>)}
              </ol>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

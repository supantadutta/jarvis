"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function HealthPage() {
  const [h, setH] = useState<any>(null);
  const [err, setErr] = useState("");
  async function load() {
    try { setH(await api.health()); setErr(""); } catch (e: any) { setErr(String(e)); }
  }
  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, []);

  async function stop(engaged: boolean) { await api.emergencyStop(engaged); load(); }

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold mb-4">Health</h1>
      {err && <p className="text-red-400">Backend unreachable: {err}</p>}
      {h && (
        <>
          <pre className="rounded border border-neutral-800 p-4 text-sm overflow-auto">
            {JSON.stringify(h, null, 2)}
          </pre>
          <div className="mt-4 flex gap-2">
            <button onClick={() => stop(true)} className="rounded bg-red-700 px-4 py-2">
              🛑 Engage Emergency Stop
            </button>
            <button onClick={() => stop(false)} className="rounded bg-neutral-700 px-4 py-2">
              Release
            </button>
          </div>
        </>
      )}
    </div>
  );
}

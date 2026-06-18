"use client";
import { useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";

export default function SettingsPage() {
  const [s, setS] = useState<any>(null);
  useEffect(() => {
    fetch(`${API_BASE}/api/settings`).then((r) => r.json()).then(setS).catch(() => {});
  }, []);
  if (!s) return <p className="text-neutral-500">Loading…</p>;
  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold mb-4">Settings</h1>
      <div className="grid grid-cols-2 gap-2 text-sm">
        {Object.entries(s).filter(([k]) => k !== "providers_configured" && k !== "allowed_domains").map(([k, v]) => (
          <div key={k} className="border-b border-neutral-800 py-1 flex justify-between">
            <span className="text-neutral-400">{k}</span><span>{String(v)}</span>
          </div>
        ))}
      </div>
      <h2 className="text-lg font-bold mt-6 mb-2">Providers configured</h2>
      <div className="flex flex-wrap gap-2">
        {Object.entries(s.providers_configured || {}).map(([k, v]) => (
          <span key={k} className={`rounded px-2 py-1 text-xs ${v ? "bg-green-800" : "bg-neutral-800 text-neutral-500"}`}>{k}</span>
        ))}
      </div>
      <p className="mt-4 text-xs text-neutral-500">Secret values are never returned by the API.</p>
    </div>
  );
}

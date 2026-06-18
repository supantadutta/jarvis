"use client";
import { useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";

export default function CredentialsPage() {
  const [creds, setCreds] = useState<any[]>([]);
  async function load() {
    try { setCreds((await (await fetch(`${API_BASE}/api/credentials`)).json()).credentials); } catch {}
  }
  useEffect(() => { load(); }, []);
  async function revoke(name: string) {
    await fetch(`${API_BASE}/api/credentials/${name}/revoke`, { method: "POST" });
    load();
  }
  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold mb-1">Credentials</h1>
      <p className="text-sm text-neutral-500 mb-4">Metadata only — secrets live in the OS keychain / encrypted vault and are never shown.</p>
      {creds.length === 0 && <p className="text-neutral-500">No credentials registered.</p>}
      <div className="space-y-2">
        {creds.map((c) => (
          <div key={c.name} className="rounded border border-neutral-800 p-3 text-sm flex justify-between items-center">
            <div>
              <div className="font-semibold">{c.name} <span className="text-xs text-neutral-500">({c.platform} · {c.kind})</span></div>
              <div className="text-xs text-neutral-500">user: {c.username} · scopes: {c.scopes?.join(", ")} {c.revoked && "· REVOKED"}</div>
            </div>
            {!c.revoked && <button onClick={() => revoke(c.name)} className="rounded bg-red-700 px-3 py-1 text-xs">Revoke</button>}
          </div>
        ))}
      </div>
    </div>
  );
}

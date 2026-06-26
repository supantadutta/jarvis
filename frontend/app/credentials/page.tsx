"use client";
import { useEffect, useState } from "react";
import { api, API_BASE } from "@/lib/api";
import { Panel } from "@/components/Hud";

export default function CredentialsPage() {
  const [creds, setCreds] = useState<any[]>([]);
  const [form, setForm] = useState<any>({ name: "", platform: "", kind: "password", username: "", secret: "" });
  const [msg, setMsg] = useState("");

  async function load() {
    try { setCreds((await (await fetch(`${API_BASE}/api/credentials`)).json()).credentials); } catch {}
  }
  useEffect(() => { load(); }, []);

  async function add() {
    setMsg("");
    try { await api.addCredential(form); setMsg(`✅ stored ${form.name}`); setForm({ ...form, name: "", platform: "", username: "", secret: "" }); load(); }
    catch (e: any) { setMsg("❌ " + String(e)); }
  }
  async function revoke(name: string) {
    await fetch(`${API_BASE}/api/credentials/${name}/revoke`, { method: "POST" }); load();
  }

  return (
    <div className="max-w-3xl space-y-5">
      <h1 className="text-2xl glow-text">Credential Vault</h1>
      <p className="label">Secrets are encrypted at rest (set VAULT_KEY) and never shown. Using a credential
        always requires your approval.</p>

      <Panel title="CONNECT A CREDENTIAL">
        <div className="grid grid-cols-2 gap-2">
          <input className="hud-input" placeholder="name (e.g. gmail)" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <input className="hud-input" placeholder="platform (e.g. google)" value={form.platform} onChange={(e) => setForm({ ...form, platform: e.target.value })} />
          <select className="hud-select" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
            {["password", "token", "oauth", "session", "api_key"].map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
          <input className="hud-input" placeholder="username (optional)" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
          <input className="hud-input col-span-2" type="password" placeholder="secret (encrypted in vault)" value={form.secret} onChange={(e) => setForm({ ...form, secret: e.target.value })} />
        </div>
        <button className="hud-btn mt-3" onClick={add}>Store</button>
        {msg && <span className="ml-3 label">{msg}</span>}
      </Panel>

      <Panel title={`STORED (${creds.length})`}>
        {creds.length === 0 && <div className="label">none registered.</div>}
        <div className="space-y-2">
          {creds.map((c) => (
            <div key={c.name} className="flex justify-between items-center border-b py-2" style={{ borderColor: "var(--line)" }}>
              <div>
                <div className="glow-text text-sm">{c.name} <span className="label">· {c.platform} · {c.kind}</span></div>
                <div className="label">user {c.username || "—"} · scopes {c.scopes?.join(",") || "—"} {c.revoked && "· REVOKED"}</div>
              </div>
              {!c.revoked && <button className="hud-btn hud-btn-ghost" style={{ borderColor: "var(--red)", color: "var(--red)" }} onClick={() => revoke(c.name)}>Revoke</button>}
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}

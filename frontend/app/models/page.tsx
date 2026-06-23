"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const KINDS = ["ollama", "openai_compatible", "openai", "anthropic", "google", "groq", "openrouter", "deepseek", "mistral", "together"];

export default function ModelsPage() {
  const [models, setModels] = useState<any[]>([]);
  const [form, setForm] = useState<any>({
    provider: "", model_name: "", kind: "openai_compatible", base_url: "", api_key: "",
    reasoning_level: 4, coding_level: 4, max_context: 32768, tool_calling_support: true,
  });
  const [msg, setMsg] = useState("");

  async function load() { try { setModels((await api.models()).models); } catch {} }
  useEffect(() => { load(); }, []);

  async function add() {
    setMsg("");
    try {
      await api.addModel(form);
      setMsg(`✅ Connected ${form.provider}/${form.model_name}`);
      setForm({ ...form, provider: "", model_name: "", api_key: "" });
      load();
    } catch (e: any) { setMsg("❌ " + String(e)); }
  }
  async function del(provider: string, model: string) {
    await api.deleteModel(provider, model); load();
  }

  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-bold mb-4">Model Registry</h1>

      <section className="rounded border border-neutral-800 p-4 mb-6">
        <h2 className="font-semibold mb-3">➕ Connect a model (any provider)</h2>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <input className="rounded bg-neutral-900 border border-neutral-700 px-2 py-1" placeholder="provider name (e.g. deepseek)"
            value={form.provider} onChange={(e) => setForm({ ...form, provider: e.target.value })} />
          <input className="rounded bg-neutral-900 border border-neutral-700 px-2 py-1" placeholder="model name (e.g. deepseek-chat)"
            value={form.model_name} onChange={(e) => setForm({ ...form, model_name: e.target.value })} />
          <select className="rounded bg-neutral-900 border border-neutral-700 px-2 py-1"
            value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
            {KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
          <input className="rounded bg-neutral-900 border border-neutral-700 px-2 py-1" placeholder="base URL (optional; auto for known)"
            value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })} />
          <input className="rounded bg-neutral-900 border border-neutral-700 px-2 py-1 col-span-2" placeholder="API key (kept in memory; never shown)"
            type="password" value={form.api_key} onChange={(e) => setForm({ ...form, api_key: e.target.value })} />
        </div>
        <button onClick={add} className="mt-3 rounded bg-blue-600 px-4 py-2 text-sm">Connect</button>
        {msg && <span className="ml-3 text-sm">{msg}</span>}
        <p className="mt-2 text-xs text-neutral-500">Tip: most providers (DeepSeek, Mistral, Together, vLLM, LM Studio, local gateways) work with kind=openai_compatible.</p>
      </section>

      <table className="w-full text-sm">
        <thead className="text-neutral-400 text-left">
          <tr><th>Model</th><th>Cost</th><th>Priv</th><th>Reason</th><th>Code</th><th>Ctx</th><th>Tools</th><th>On</th><th></th></tr>
        </thead>
        <tbody>
          {models.map((m) => (
            <tr key={m.key} className="border-t border-neutral-800">
              <td className="py-2">{m.display_name}<div className="text-xs text-neutral-500">{m.key}</div></td>
              <td>{m.cost_type}</td><td>{m.privacy_level}</td>
              <td>{m.reasoning_level}</td><td>{m.coding_level}</td><td>{m.max_context}</td>
              <td>{m.tool_calling_support ? "✓" : "—"}</td>
              <td>{m.enabled ? "🟢" : "⚪"}</td>
              <td><button onClick={() => del(m.provider, m.model_name)} className="text-xs text-red-400">remove</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

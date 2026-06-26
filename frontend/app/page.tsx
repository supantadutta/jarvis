"use client";
import { useEffect, useRef, useState } from "react";
import { api, API_BASE } from "@/lib/api";
import { ArcReactor, Panel, Stat, StatusDot } from "@/components/Hud";

const EXEC = [
  ["auto", "AUTO"], ["chat", "CHAT"], ["autonomous", "AGENT"], ["graph", "GRAPH"],
];

export default function Console() {
  const [cmd, setCmd] = useState("");
  const [exec, setExec] = useState("auto");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [status, setStatus] = useState<any>(null);
  const [events, setEvents] = useState<any[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  async function loadStatus() { try { setStatus(await api.brainStatus()); } catch {} }

  useEffect(() => {
    loadStatus();
    const t = setInterval(loadStatus, 6000);
    // Live activity timeline via WebSocket.
    try {
      const url = API_BASE.replace(/^http/, "ws") + "/api/ws/events";
      const ws = new WebSocket(url);
      wsRef.current = ws;
      ws.onmessage = (m) => {
        const msg = JSON.parse(m.data);
        if (msg.type === "snapshot") setEvents((msg.events || []).slice(-12).reverse());
        else setEvents((e) => [msg, ...e].slice(0, 30));
      };
    } catch {}
    return () => { clearInterval(t); wsRef.current?.close(); };
  }, []);

  async function run() {
    if (!cmd.trim()) return;
    setBusy(true); setResult(null);
    try { setResult(await api.brainRun(cmd, exec)); }
    catch (e: any) { setResult({ error: String(e) }); }
    setBusy(false); loadStatus();
  }

  const r = status?.resources;
  return (
    <div className="space-y-5">
      {/* Hero command bar */}
      <Panel className="glow-border">
        <div className="flex items-center gap-4">
          <ArcReactor size={56} active={busy} />
          <div className="flex-1">
            <div className="label mb-1">Cognitive Command Interface</div>
            <input className="hud-input w-full text-lg" placeholder="Give JARVIS an objective…"
              value={cmd} onChange={(e) => setCmd(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && run()} />
          </div>
          <select className="hud-select" value={exec} onChange={(e) => setExec(e.target.value)}>
            {EXEC.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <button className="hud-btn" onClick={run} disabled={busy}>
            {busy ? "PROCESSING" : "EXECUTE"}</button>
        </div>
      </Panel>

      {/* Vitals */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        <Stat label="Models" value={status?.models_enabled ?? "—"} />
        <Stat label="Cache hit" value={r ? `${Math.round((status.response_cache.hit_rate || 0) * 100)}%` : "—"} />
        <Stat label="CPU" value={r?.cpu_count ?? "—"} />
        <Stat label="RAM GB" value={r?.ram_gb ?? "—"} />
        <Stat label="GPU" value={r ? (r.gpu ? "YES" : "—") : "—"} color={r?.gpu ? "var(--green)" : "var(--muted)"} />
        <Stat label="Queue" value={status?.queue?.jobs ?? "—"} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Result */}
        <div className="lg:col-span-2 space-y-5">
          {result && !result.error && (
            <Panel title={`OUTPUT · ${String(result.kind).toUpperCase()}`}
              right={<span className="hud-chip">{result.analysis?.task_type}</span>}>
              <div className="whitespace-pre-wrap mb-3">{result.answer}</div>
              <div className="flex flex-wrap gap-2 mb-2">
                {result.quality && <span className="hud-chip">quality {Math.round((result.quality.scores?.completeness || 0) * 100)}%</span>}
                {result.groundedness && <span className="hud-chip">grounded {Math.round((result.groundedness.score || 0) * 100)}%</span>}
                {result.analysis && <span className="hud-chip">risk {result.analysis.risk_level}</span>}
                {result.budget && <span className="hud-chip">actions {result.budget.actions_used}</span>}
              </div>
              {result.detail?.steps && (
                <ol className="space-y-1 mt-2">
                  {result.detail.steps.map((s: any, i: number) => (
                    <li key={i} className="label">▸ {s.tool || s.node_id} <span style={{ color: s.decision === "deny" ? "var(--red)" : s.status === "completed" ? "var(--green)" : "var(--amber)" }}>{s.decision || s.status}</span></li>
                  ))}
                </ol>
              )}
            </Panel>
          )}
          {result?.error && <Panel><div style={{ color: "var(--red)" }}>{result.error}</div></Panel>}
          {!result && (
            <Panel title="STANDING BY">
              <div className="label">Issue an objective. AUTO routes it to the right engine —
                CHAT (answer), AGENT (act with tools), or GRAPH (multi-step plan). Every action
                passes the Permission Guard; risky steps await your approval.</div>
            </Panel>
          )}
        </div>

        {/* Live activity timeline */}
        <Panel title="ACTIVITY STREAM" right={<StatusDot ok={!!wsRef.current} />}>
          <div className="space-y-1 max-h-[460px] overflow-y-auto">
            {events.length === 0 && <div className="label">awaiting telemetry…</div>}
            {events.map((e, i) => (
              <div key={i} className="text-xs border-b py-1" style={{ borderColor: "var(--line)" }}>
                <span className="glow-text">{e.agent || e.tool || e.type}</span>
                <span className="label"> {e.tool ? `· ${e.tool}` : ""} · {e.risk || ""}</span>
                <div className="label truncate">{e.summary}</div>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}

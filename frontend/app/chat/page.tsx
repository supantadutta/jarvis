"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { Panel } from "@/components/Hud";

const MODES = ["SINGLE_BEST_MODEL","FAST_MODE","DEEP_WORK_MODE","PRIVATE_MODE","PARALLEL_MODE","DEBATE_MODE","VERIFIER_MODE","COST_SAVER_MODE"];

export default function ChatPage() {
  const [message, setMessage] = useState("");
  const [mode, setMode] = useState("");
  const [stream, setStream] = useState(true);
  const [log, setLog] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [streaming, setStreaming] = useState("");

  async function send() {
    if (!message.trim()) return;
    setBusy(true); const cmd = message; setMessage("");
    try {
      if (stream) {
        setStreaming(""); let acc = "";
        const meta: any = { cmd, res: { answer: "", models: [], mode: "" } };
        await api.chatStream(cmd, mode || undefined, (ev, data) => {
          if (ev === "classified") meta.res.mode = data.mode;
          if (ev === "routed") meta.res.models = data.models;
          if (ev === "token") { acc += data.text; setStreaming(acc); }
          if (ev === "done") { meta.res.answer = acc; meta.res = { ...meta.res, ...data }; }
        });
        setStreaming(""); setLog((l) => [meta, ...l]);
      } else {
        const res = await api.chat(cmd, mode || undefined);
        setLog((l) => [{ cmd, res }, ...l]);
      }
    } catch (e: any) { setLog((l) => [{ cmd, error: String(e) }, ...l]); }
    finally { setBusy(false); }
  }

  return (
    <div className="max-w-3xl space-y-4">
      <h1 className="text-2xl glow-text">Direct Channel</h1>
      <div className="flex gap-2">
        <input className="hud-input flex-1" placeholder="Transmit to JARVIS…"
          value={message} onChange={(e) => setMessage(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()} />
        <select className="hud-select" value={mode} onChange={(e) => setMode(e.target.value)}>
          <option value="">auto</option>
          {MODES.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
        <button className="hud-btn" onClick={send} disabled={busy}>{busy ? "…" : "Send"}</button>
      </div>
      <label className="flex items-center gap-2 label">
        <input type="checkbox" checked={stream} onChange={(e) => setStream(e.target.checked)} /> stream (SSE)
      </label>
      {streaming && <Panel><div className="whitespace-pre-wrap">{streaming}<span className="animate-pulse glow-text">▌</span></div></Panel>}
      <div className="space-y-3">
        {log.map((entry, i) => (
          <Panel key={i}>
            <div className="label">▸ {entry.cmd}</div>
            {entry.error ? <div className="mt-2" style={{ color: "var(--red)" }}>{entry.error}</div> : (
              <>
                <div className="mt-2 whitespace-pre-wrap">{entry.res.answer}</div>
                <div className="mt-2 label">mode={entry.res.mode} · models={entry.res.models?.join(", ")}
                  {entry.res.pending_approvals?.length > 0 && ` · ⚠ approvals: ${entry.res.pending_approvals.join(", ")}`}</div>
              </>
            )}
          </Panel>
        ))}
      </div>
    </div>
  );
}

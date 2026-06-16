"use client";
import { useState } from "react";
import { api } from "@/lib/api";

const MODES = [
  "SINGLE_BEST_MODEL", "FAST_MODE", "DEEP_WORK_MODE", "PRIVATE_MODE",
  "PARALLEL_MODE", "DEBATE_MODE", "VERIFIER_MODE", "COST_SAVER_MODE",
];

export default function ChatPage() {
  const [message, setMessage] = useState("");
  const [mode, setMode] = useState("");
  const [stream, setStream] = useState(true);
  const [log, setLog] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [streaming, setStreaming] = useState("");

  async function send() {
    if (!message.trim()) return;
    setBusy(true);
    const cmd = message;
    setMessage("");
    try {
      if (stream) {
        setStreaming("");
        let acc = "";
        const meta: any = { cmd, res: { answer: "", models: [], mode: "", task_type: "" } };
        await api.chatStream(cmd, mode || undefined, (ev, data) => {
          if (ev === "classified") meta.res.mode = data.mode;
          if (ev === "routed") meta.res.models = data.models;
          if (ev === "token") { acc += data.text; setStreaming(acc); }
          if (ev === "done") { meta.res.answer = acc; meta.res = { ...meta.res, ...data }; }
        });
        setStreaming("");
        setLog((l) => [meta, ...l]);
      } else {
        const res = await api.chat(cmd, mode || undefined);
        setLog((l) => [{ cmd, res }, ...l]);
      }
    } catch (e: any) {
      setLog((l) => [{ cmd, error: String(e) }, ...l]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold mb-4">Chat</h1>
      <div className="flex gap-2 mb-4">
        <input
          className="flex-1 rounded bg-neutral-900 border border-neutral-700 px-3 py-2"
          placeholder="Ask JARVIS… (e.g. 'deep work: plan my SOC lab')"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
        />
        <select
          className="rounded bg-neutral-900 border border-neutral-700 px-2"
          value={mode}
          onChange={(e) => setMode(e.target.value)}
        >
          <option value="">auto-mode</option>
          {MODES.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
        <button
          onClick={send}
          disabled={busy}
          className="rounded bg-blue-600 px-4 py-2 disabled:opacity-50"
        >
          {busy ? "…" : "Send"}
        </button>
      </div>

      <label className="flex items-center gap-2 text-xs text-neutral-400 mb-4">
        <input type="checkbox" checked={stream} onChange={(e) => setStream(e.target.checked)} />
        stream responses (SSE)
      </label>

      {streaming && (
        <div className="rounded border border-blue-900 bg-neutral-900/50 p-4 mb-4 whitespace-pre-wrap">
          {streaming}<span className="animate-pulse">▌</span>
        </div>
      )}

      <div className="space-y-4">
        {log.map((entry, i) => (
          <div key={i} className="rounded border border-neutral-800 p-4">
            <div className="text-sm text-neutral-400">You: {entry.cmd}</div>
            {entry.error ? (
              <div className="text-red-400 mt-2">{entry.error}</div>
            ) : (
              <>
                <div className="mt-2 whitespace-pre-wrap">{entry.res.answer}</div>
                <div className="mt-3 text-xs text-neutral-500">
                  mode={entry.res.mode} · type={entry.res.task_type} · models={entry.res.models?.join(", ")}
                  {entry.res.verifier && ` · verified=${entry.res.verifier.passed}`}
                  {entry.res.pending_approvals?.length > 0 &&
                    ` · ⚠ approvals: ${entry.res.pending_approvals.join(", ")}`}
                </div>
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

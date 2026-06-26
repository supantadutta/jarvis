"use client";
import { useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";
import { StatusDot } from "./Hud";

export default function TopBar() {
  const [h, setH] = useState<any>(null);
  const [online, setOnline] = useState(false);
  const [clock, setClock] = useState("");

  useEffect(() => {
    const tick = async () => {
      try {
        const r = await fetch(`${API_BASE}/api/health`);
        const j = await r.json();
        setH(j); setOnline(true);
      } catch { setOnline(false); }
    };
    tick();
    const t = setInterval(tick, 5000);
    const ct = setInterval(() => setClock(new Date().toLocaleTimeString()), 1000);
    return () => { clearInterval(t); clearInterval(ct); };
  }, []);

  return (
    <div className="flex items-center justify-between px-6 py-2 border-b text-xs"
      style={{ borderColor: "var(--line)", background: "rgba(4,7,14,0.6)" }}>
      <div className="flex items-center gap-4">
        <span className="flex items-center gap-2"><StatusDot ok={online} />
          <span className="label">{online ? "SYSTEMS NOMINAL" : "LINK LOST"}</span></span>
        {h && <span className="label">MODELS {h.models_enabled} · TOOLS {h.tools} · AGENTS {h.agents}</span>}
        {h?.emergency_stop && <span className="hud-chip" style={{ color: "var(--red)", borderColor: "var(--red)" }}>E-STOP</span>}
      </div>
      <div className="flex items-center gap-4">
        {h && <span className="label">APPROVALS {h.pending_approvals}</span>}
        <span className="glow-text">{clock}</span>
      </div>
    </div>
  );
}

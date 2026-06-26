"use client";
import { ReactNode } from "react";

export function ArcReactor({ size = 44, active = true }: { size?: number; active?: boolean }) {
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" className="flicker">
      <defs>
        <radialGradient id="core" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#eafdff" />
          <stop offset="55%" stopColor="#22d3ee" />
          <stop offset="100%" stopColor="#0e7490" />
        </radialGradient>
      </defs>
      <circle cx="50" cy="50" r="46" fill="none" stroke="#155e75" strokeWidth="2" opacity="0.5" />
      <g className={active ? "reactor-spin" : ""} stroke="#22d3ee" strokeWidth="2" fill="none" opacity="0.8">
        {Array.from({ length: 10 }).map((_, i) => (
          <line key={i} x1="50" y1="14" x2="50" y2="24"
            transform={`rotate(${i * 36} 50 50)`} />
        ))}
      </g>
      <g className={active ? "reactor-spin-rev" : ""} stroke="#3b82f6" strokeWidth="1.5" fill="none" opacity="0.6">
        <polygon points="50,26 71,62 29,62" />
      </g>
      <circle cx="50" cy="50" r="13" fill="url(#core)" />
      <circle cx="50" cy="50" r="13" fill="none" stroke="#eafdff" strokeWidth="1.5" opacity="0.9" />
    </svg>
  );
}

export function Panel({ title, right, children, className = "" }:
  { title?: string; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`hud-panel p-4 ${className}`}>
      {(title || right) && (
        <div className="flex items-center justify-between mb-3">
          {title && <h2 className="text-sm glow-text">{title}</h2>}
          {right}
        </div>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, color = "var(--cyan-bright)" }:
  { label: string; value: ReactNode; color?: string }) {
  return (
    <div className="hud-panel px-3 py-2">
      <div className="label">{label}</div>
      <div className="text-lg" style={{ color, textShadow: `0 0 8px ${color}` }}>{value}</div>
    </div>
  );
}

export function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span className="pulse-dot inline-block w-2 h-2 rounded-full"
      style={{ background: ok ? "var(--green)" : "var(--red)",
               boxShadow: `0 0 8px ${ok ? "var(--green)" : "var(--red)"}` }} />
  );
}

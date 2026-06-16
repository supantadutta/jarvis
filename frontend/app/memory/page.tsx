"use client";
import { useState } from "react";
import { api } from "@/lib/api";

export default function MemoryPage() {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<any[]>([]);
  async function search() { try { setHits((await api.memorySearch(q)).hits); } catch {} }
  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold mb-4">Memory Search</h1>
      <div className="flex gap-2 mb-4">
        <input className="flex-1 rounded bg-neutral-900 border border-neutral-700 px-3 py-2"
          value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && search()} placeholder="Search local memory…" />
        <button onClick={search} className="rounded bg-blue-600 px-4 py-2">Search</button>
      </div>
      <div className="space-y-2">
        {hits.map((h) => (
          <div key={h.id} className="rounded border border-neutral-800 p-3 text-sm">
            <div className="text-xs text-neutral-500">score={h.score} {h.source && `· ${h.source}`}</div>
            <div>{h.text}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

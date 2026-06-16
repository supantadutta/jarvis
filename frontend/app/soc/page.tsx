"use client";
import { useState } from "react";
import { API_BASE } from "@/lib/api";

async function post(path: string, body: any) {
  const r = await fetch(`${API_BASE}/api${path}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  return r.json();
}
async function get(path: string) {
  const r = await fetch(`${API_BASE}/api${path}`);
  return r.json();
}

export default function SocPage() {
  const [eid, setEid] = useState("4625");
  const [eventOut, setEventOut] = useState<any>(null);
  const [behavior, setBehavior] = useState("failed logons then RDP lateral movement");
  const [attack, setAttack] = useState<any[]>([]);
  const [splunk, setSplunk] = useState<any>(null);

  return (
    <div className="max-w-3xl space-y-8">
      <div>
        <h1 className="text-2xl font-bold mb-1">SOC (defensive)</h1>
        <p className="text-sm text-neutral-500">Detection engineering & analysis — lab-authorized only.</p>
      </div>

      <section className="rounded border border-neutral-800 p-4">
        <h2 className="font-semibold mb-2">Windows Event ID</h2>
        <div className="flex gap-2">
          <input className="rounded bg-neutral-900 border border-neutral-700 px-3 py-1 w-32"
            value={eid} onChange={(e) => setEid(e.target.value)} />
          <button className="rounded bg-blue-600 px-3 py-1 text-sm"
            onClick={async () => setEventOut(await get(`/soc/event/${eid}`))}>Explain</button>
        </div>
        {eventOut && <pre className="mt-2 text-xs">{JSON.stringify(eventOut, null, 2)}</pre>}
      </section>

      <section className="rounded border border-neutral-800 p-4">
        <h2 className="font-semibold mb-2">MITRE ATT&CK mapping</h2>
        <div className="flex gap-2">
          <input className="flex-1 rounded bg-neutral-900 border border-neutral-700 px-3 py-1"
            value={behavior} onChange={(e) => setBehavior(e.target.value)} />
          <button className="rounded bg-blue-600 px-3 py-1 text-sm"
            onClick={async () => setAttack((await post("/soc/attack-map", { behavior })).techniques)}>Map</button>
        </div>
        <div className="mt-2 space-y-1">
          {attack.map((t) => (
            <div key={t.technique_id} className="text-sm">
              <b>{t.technique_id}</b> {t.name} <span className="text-neutral-500">({t.tactic})</span>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded border border-neutral-800 p-4">
        <h2 className="font-semibold mb-2">Splunk / LogScale query (failed logons by src_ip)</h2>
        <button className="rounded bg-blue-600 px-3 py-1 text-sm"
          onClick={async () => setSplunk(await post("/soc/splunk", { index: "wineventlog", event_id: 4625, by_fields: ["src_ip"], threshold: 10 }))}>Build</button>
        {splunk && (
          <div className="mt-2 text-xs space-y-2">
            <div><span className="text-neutral-500">SPL:</span> <code>{splunk.spl}</code></div>
            <div><span className="text-neutral-500">LogScale:</span> <code>{splunk.logscale}</code></div>
          </div>
        )}
      </section>
    </div>
  );
}

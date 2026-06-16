"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function ModelsPage() {
  const [models, setModels] = useState<any[]>([]);
  useEffect(() => { api.models().then((d) => setModels(d.models)).catch(() => {}); }, []);
  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Model Registry</h1>
      <table className="w-full text-sm">
        <thead className="text-neutral-400 text-left">
          <tr><th>Model</th><th>Cost</th><th>Priv</th><th>Speed</th><th>Reason</th><th>Code</th><th>Ctx</th><th>Tools</th><th>On</th></tr>
        </thead>
        <tbody>
          {models.map((m) => (
            <tr key={m.key} className="border-t border-neutral-800">
              <td className="py-2">{m.display_name}<div className="text-xs text-neutral-500">{m.key}</div></td>
              <td>{m.cost_type}</td><td>{m.privacy_level}</td><td>{m.speed_level}</td>
              <td>{m.reasoning_level}</td><td>{m.coding_level}</td><td>{m.max_context}</td>
              <td>{m.tool_calling_support ? "✓" : "—"}</td>
              <td>{m.enabled ? "🟢" : "⚪"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function ToolsPage() {
  const [tools, setTools] = useState<any[]>([]);
  useEffect(() => { api.tools().then((d) => setTools(d.tools)).catch(() => {}); }, []);
  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-bold mb-4">Tool Registry ({tools.length})</h1>
      <table className="w-full text-sm">
        <thead className="text-neutral-400 text-left"><tr><th>Tool</th><th>Permission</th><th>Risk</th><th>Approval</th></tr></thead>
        <tbody>
          {tools.map((t) => (
            <tr key={t.name} className="border-t border-neutral-800">
              <td className="py-2 font-mono">{t.name}<div className="text-xs text-neutral-500">{t.description}</div></td>
              <td>{t.permission}</td><td>{t.risk}</td>
              <td>{t.requires_approval || ["BROWSER_WRITE","DESKTOP_CONTROL","CREDENTIAL_ACCESS","HIGH_RISK","TERMINAL_WRITE"].includes(t.permission) ? "required" : "auto"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

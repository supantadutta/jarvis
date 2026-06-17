"use client";
import { useState } from "react";
import { api } from "@/lib/api";

export default function DocumentsPage() {
  const [title, setTitle] = useState("My Report");
  const [content, setContent] = useState("Hello from JARVIS.");
  const [format, setFormat] = useState("md");
  const [out, setOut] = useState<any>(null);

  async function gen() {
    try { setOut(await api.generateDocument({ title, content, format })); }
    catch (e: any) { setOut({ error: String(e) }); }
  }

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold mb-4">Document Generator</h1>
      <input className="w-full mb-2 rounded bg-neutral-900 border border-neutral-700 px-3 py-2"
        value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title" />
      <textarea className="w-full h-40 mb-2 rounded bg-neutral-900 border border-neutral-700 px-3 py-2"
        value={content} onChange={(e) => setContent(e.target.value)} placeholder="Content" />
      <div className="flex gap-2 items-center">
        <select className="rounded bg-neutral-900 border border-neutral-700 px-2 py-2"
          value={format} onChange={(e) => setFormat(e.target.value)}>
          {["md", "docx", "pdf", "xlsx"].map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
        <button onClick={gen} className="rounded bg-blue-600 px-4 py-2">Generate</button>
      </div>
      {out && <pre className="mt-4 text-sm rounded border border-neutral-800 p-3">{JSON.stringify(out, null, 2)}</pre>}
    </div>
  );
}

// Minimal API client for the JARVIS backend.
export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
// Optional API token (set NEXT_PUBLIC_API_TOKEN when the backend has auth on).
const API_TOKEN = process.env.NEXT_PUBLIC_API_TOKEN || "";

export function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const h: Record<string, string> = { "Content-Type": "application/json", ...extra };
  if (API_TOKEN) h["Authorization"] = `Bearer ${API_TOKEN}`;
  return h;
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}/api${path}`, {
    cache: "no-store",
    ...init,
    headers: authHeaders((init?.headers as Record<string, string>) || {}),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  health: () => http<any>("/health"),
  chat: (message: string, mode?: string) =>
    http<any>("/chat", { method: "POST", body: JSON.stringify({ message, mode }) }),

  // SSE streaming: invokes onEvent(eventName, data) per server-sent event.
  chatStream: async (
    message: string,
    mode: string | undefined,
    onEvent: (event: string, data: any) => void,
  ) => {
    const res = await fetch(`${API_BASE}/api/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, mode }),
    });
    if (!res.body) throw new Error("No stream body");
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const blocks = buf.split("\n\n");
      buf = blocks.pop() || "";
      for (const block of blocks) {
        const ev = block.match(/^event: (.*)$/m)?.[1];
        const dataLine = block.match(/^data: (.*)$/m)?.[1];
        if (ev && dataLine) onEvent(ev, JSON.parse(dataLine));
      }
    }
  },
  models: () => http<any>("/models"),
  agents: () => http<any>("/agents"),
  tools: () => http<any>("/tools"),
  tasks: () => http<any>("/tasks"),
  approvals: () => http<any>("/approvals"),
  decideApproval: (id: string, approved: boolean, trust = false) =>
    http<any>(`/approvals/${id}/decision`, {
      method: "POST",
      body: JSON.stringify({ approved, trust }),
    }),
  audit: (limit = 100) => http<any>(`/audit?limit=${limit}`),
  workflows: () => http<any>("/workflows"),
  runWorkflow: (key: string) => http<any>(`/workflows/${key}/run`, { method: "POST" }),
  workflowRuns: () => http<any>("/workflows/runs"),
  memorySearch: (query: string) =>
    http<any>("/memory/search", { method: "POST", body: JSON.stringify({ query }) }),
  emergencyStop: (engaged: boolean) =>
    http<any>("/control/stop", { method: "POST", body: JSON.stringify({ engaged }) }),
  evaluations: () => http<any>("/evaluations"),
  plugins: () => http<any>("/plugins"),
  generateDocument: (body: any) =>
    http<any>("/documents/generate", { method: "POST", body: JSON.stringify(body) }),
  socEvent: (id: number) => http<any>(`/soc/event/${id}`),
  addModel: (body: any) =>
    http<any>("/models", { method: "POST", body: JSON.stringify(body) }),
  deleteModel: (provider: string, model: string) =>
    http<any>(`/models/${provider}/${model}`, { method: "DELETE" }),
  providers: () => http<any>("/providers"),
  learn: (topic: string, maxSources = 3) =>
    http<any>("/learn", { method: "POST", body: JSON.stringify({ topic, max_sources: maxSources }) }),
  agentRun: (goal: string, maxSteps = 8) =>
    http<any>("/agent/run", { method: "POST", body: JSON.stringify({ goal, max_steps: maxSteps }) }),
  brainAnalyze: (command: string) =>
    http<any>("/brain/analyze", { method: "POST", body: JSON.stringify({ command }) }),
  brainPlan: (command: string) =>
    http<any>("/brain/plan", { method: "POST", body: JSON.stringify({ command }) }),
  brainExecute: (command: string, background = false) =>
    http<any>("/brain/execute", { method: "POST", body: JSON.stringify({ command, background }) }),
  brainStatus: () => http<any>("/brain/status"),
  brainBenchmarks: () => http<any>("/brain/benchmarks/run", { method: "POST" }),
};

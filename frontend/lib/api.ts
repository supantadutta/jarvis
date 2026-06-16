// Minimal API client for the JARVIS backend.
export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}/api${path}`, {
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    ...init,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  health: () => http<any>("/health"),
  chat: (message: string, mode?: string) =>
    http<any>("/chat", { method: "POST", body: JSON.stringify({ message, mode }) }),
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
  memorySearch: (query: string) =>
    http<any>("/memory/search", { method: "POST", body: JSON.stringify({ query }) }),
  emergencyStop: (engaged: boolean) =>
    http<any>("/control/stop", { method: "POST", body: JSON.stringify({ engaged }) }),
};

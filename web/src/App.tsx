import { useEffect, useState } from "react";
import type { components } from "./api/schema";

type Health = components["schemas"]["Health"];

const API = "http://localhost:8000";

export function App() {
  const [health, setHealth] = useState<Health | "down" | null>(null);

  useEffect(() => {
    fetch(`${API}/health`)
      .then((r) => r.json() as Promise<Health>)
      .then(setHealth)
      .catch(() => setHealth("down"));
  }, []);

  const status =
    health === null ? "connecting…" : health === "down" ? "unreachable" : `ok (v${health.version})`;

  return (
    <main className="min-h-screen bg-slate-950 p-6 text-slate-100">
      <h1 className="text-3xl font-bold">ResQ-AI</h1>
      <p className="mt-2">API: {status}</p>
    </main>
  );
}

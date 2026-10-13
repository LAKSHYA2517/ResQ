import type { components } from "./schema";

type S = components["schemas"];
export type Cell = [number, number];
export type Snapshot = S["SnapshotOut"];
export type GridState = S["StateOut"];
export type Scenario = S["ScenarioModel"];
export type ScenarioSummary = S["ScenarioSummary"];
export type Issue = S["IssueOut"];
export type Validation = S["ValidationOut"];
export type Session = S["SessionOut"];
export type EventResult = S["EventOut"];
export type EventTypeName = S["EventIn"]["type"];
export type LogEntry = S["LogEntryOut"];
export type Rule = components["schemas"]["RuleOut"];
export type Compare = components["schemas"]["CompareOut"];
export type SearchRun = components["schemas"]["SearchRunOut"];
export type RunSpec = components["schemas"]["RunSpec"];

export const API_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
export const WS_URL = API_URL.replace(/^http/, "ws");

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly body: unknown,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError(
      `Cannot reach the engine API at ${API_URL}. Is \`make dev\` running?`,
      0,
      null,
    );
  }
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body ? String(body.detail) : res.statusText;
    throw new ApiError(detail, res.status, body);
  }
  return body as T;
}

const post = <T>(path: string, body: unknown) =>
  request<T>(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });

const qs = (params: Record<string, string | number | boolean | undefined>) => {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined) q.set(k, String(v));
  return `?${q}`;
};

export const api = {
  health: () => request<S["Health"]>("/health"),
  scenarios: () => request<ScenarioSummary[]>("/scenarios"),
  scenario: (id: string) => request<S["ScenarioOut"]>(`/scenario/${id}`),
  validate: (scenario: Scenario) => post<Validation>("/scenario/validate", scenario),
  create: (scenario: Scenario) => post<S["ScenarioOut"]>("/scenario", scenario),
  start: (scenario_id: string, seed?: number) =>
    post<Session>("/simulation/start", { scenario_id, seed }),
  step: (session_id: string) => post<Snapshot>("/simulation/step", { session_id }),
  reset: (session_id: string) => post<Snapshot>("/simulation/reset", { session_id }),
  event: (session_id: string, type: EventTypeName, args: Record<string, unknown>) =>
    post<EventResult>("/simulation/event", { session_id, type, args }),
  run: (session_id: string, speed: number) =>
    post<S["RunOut"]>(`/simulation/run${qs({ speed })}`, { session_id }),
  replay: (session_id: string, tick: number) =>
    request<Snapshot>(`/simulation/replay/${tick}${qs({ session_id })}`),
  log: (session_id: string) => request<LogEntry[]>(`/simulation/log${qs({ session_id })}`),
  rules: () => request<Rule[]>("/kb/rules"),
  compare: (body: { session_id: string; tick?: number; target?: string; runs?: RunSpec[] }) =>
    post<Compare>("/search/compare", body),
};

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
export type Rule = S["RuleOut"];
export type Compare = S["CompareOut"];
export type SearchRun = S["SearchRunOut"];
export type RunSpec = S["RunSpec"];
export type AlgorithmName = RunSpec["algorithm"];
export type HeuristicName = NonNullable<RunSpec["heuristic"]>;
export type HeuristicCheck = S["HeuristicOut"];
export type KbQuery = S["QueryOut"];
export type ProofNode = S["ProofNodeOut"];
export type Network = S["NetworkModel"];
export type Inference = S["InferOut"];
export type OrderReport = S["OrderOut"];
export type Adversarial = S["AdversarialOut"];
export type PlanCompare = S["PlanCompareOut"];
export type Profile = S["ProfileOut"];
export type Belief = S["BeliefOut"];
export type FireMode = S["SessionOut"]["fire_mode"];

/** Request bodies: the API fills in every default, so only `session_id` is required. */
type In<K extends keyof S> = Partial<S[K]> & { session_id: string };

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
  start: (scenario_id: string, seed?: number, fire_mode?: FireMode) =>
    post<Session>("/simulation/start", { scenario_id, seed, fire_mode }),
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
  compare: (body: In<"CompareIn">) => post<Compare>("/search/compare", body),
  heuristicCheck: (body: In<"HeuristicIn">) =>
    post<HeuristicCheck>("/search/heuristic-check", body),
  kbQuery: (session_id: string, goal: string, tick?: number) =>
    post<KbQuery>("/kb/query", { session_id, goal, tick }),
  network: (prior: number) => request<Network>(`/bayes/network${qs({ prior })}`),
  infer: (body: Partial<S["InferIn"]>) => post<Inference>("/bayes/infer", body),
  order: (body: In<"OrderIn">) => post<OrderReport>("/optimize/order", body),
  adversarial: (body: In<"AdversarialIn">) => post<Adversarial>("/adversarial/move", body),
  planCompare: (body: In<"PlanCompareIn">) => post<PlanCompare>("/plan/compare", body),
  profile: (session_id: string) => request<Profile>(`/agent/profile${qs({ session_id })}`),
};

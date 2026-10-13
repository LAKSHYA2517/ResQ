import type { Snapshot } from "../api/client";

export type TraceEvent = Snapshot["trace"][number];

const d = (e: TraceEvent, k: string) => e.data[k];
const cell = (v: unknown) => (Array.isArray(v) ? `(${v.join(", ")})` : String(v));
const list = (v: unknown) => (Array.isArray(v) ? v.join(" → ") : String(v));
const num = (v: unknown) =>
  typeof v === "number" ? (Number.isInteger(v) ? v : v.toFixed(1)) : "–";

/** One readable line per engine trace event. Wording only; every number comes from the event. */
export function describe(e: TraceEvent): string {
  switch (e.kind) {
    case "RouteComputed":
      return d(e, "found")
        ? `A* ${cell(d(e, "src"))} → ${cell(d(e, "dst"))}: cost ${num(d(e, "cost"))}, ` +
            `${d(e, "expanded")} expanded, ${d(e, "generated")} generated`
        : `A* ${cell(d(e, "src"))} → ${cell(d(e, "dst"))}: no route (${d(e, "expanded")} expanded)`;
    case "TargetChosen":
      return `target ${d(e, "target") ?? "none"}${d(e, "switched") ? " (switched)" : ""}: ${d(e, "reason")}`;
    case "PlanFound":
      return `plan found, cost ${num(d(e, "cost"))}, ${d(e, "expanded")} states expanded: ${list(d(e, "steps"))}`;
    case "PlanFailed":
      return `planner failed after ${d(e, "expanded")} states: ${d(e, "reason")}`;
    case "PlanInvalidated":
      return `plan invalidated: ${d(e, "reason")}`;
    case "PlanAdopted":
      return `plan adopted (${d(e, "change")}), cost ${num(d(e, "cost"))}: ${list(d(e, "steps"))}`;
    case "NoValidPlan":
      return `no valid plan: ${list(d(e, "reasons"))}`;
    case "ActionExecuted":
      return `${d(e, "action")}: ${d(e, "detail")} (cost ${num(d(e, "cost"))})`;
    case "ActionFailed":
      return `action ${d(e, "action")} refused: ${d(e, "reason")}`;
    case "EventApplied":
      return `event ${d(e, "event_type")} ${JSON.stringify(d(e, "args"))}`;
    case "EventRejected":
      return `event ${d(e, "event_type")} ${JSON.stringify(d(e, "args"))} refused: ${d(e, "reason")}`;
    case "FireSpread":
      return `fire spread to ${(d(e, "ignited") as unknown[]).length} cell(s)`;
    case "PersonStatusChanged":
      return `${d(e, "person_id")}: ${d(e, "old")} → ${d(e, "new")}`;
    default:
      return `${e.kind} ${JSON.stringify(e.data)}`;
  }
}

export const eventsOf = (s: Snapshot, ...kinds: string[]) =>
  s.trace.filter((e) => kinds.includes(e.kind));

/** Stable React keys for a list that may legitimately repeat a line (same search run twice). */
export function keyed(events: TraceEvent[]): { key: string; event: TraceEvent; text: string }[] {
  const seen = new Map<string, number>();
  return events.map((event) => {
    const text = describe(event);
    const n = (seen.get(text) ?? 0) + 1;
    seen.set(text, n);
    return { key: `${text}#${n}`, event, text };
  });
}

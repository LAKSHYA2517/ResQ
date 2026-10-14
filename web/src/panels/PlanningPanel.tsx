import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { Btn, Chip, Empty, fmt, Section } from "../components/ui";
import { eventsOf } from "../lib/trace";
import { useSim, useView } from "../store/sim";
import { useUi } from "../store/ui";

const ICON = { done: "✓", current: "▶", pending: "○" } as const;

export function PlanningPanel() {
  const view = useView();
  const setExplain = useUi((s) => s.setExplain);
  if (!view) return <Empty>Start a scenario to see the agent's goal and plan.</Empty>;

  const change = view.plan_change;
  const found = eventsOf(view, "PlanFound").at(-1);
  const chosen = eventsOf(view, "TargetChosen").at(-1);
  const total = view.plan.reduce((a, s) => a + s.cost, 0);
  const goalPerson = view.target ? view.state.people.find((p) => p.id === view.target) : null;

  return (
    <div className="h-full overflow-y-auto">
      <Section
        title="Goal"
        right={
          view.target && <Btn onClick={() => setExplain("decision")}>Explain this decision</Btn>
        }
      >
        {view.status === "complete" && (
          <p className="text-sm text-go">Everyone is evacuated. Nothing left to plan.</p>
        )}
        {view.status === "stuck" && (
          <p className="text-sm text-warn">No valid plan right now (see the reasons below).</p>
        )}
        {view.status === "running" && view.target && (
          <p className="text-sm">
            Achieve <span className="font-mono text-accent">Evacuated({view.target})</span>
            {goalPerson && (
              <span className="text-dim">
                {" "}
                — {goalPerson.status.toLowerCase()} at ({goalPerson.pos.join(", ")})
              </span>
            )}
          </p>
        )}
        {chosen && <p className="mt-1 text-xs text-dim">{String(chosen.data.reason)}</p>}
      </Section>

      <Section title="Priority scores">
        <p className="mb-2 font-mono text-xs text-dim">
          Priority = w_r·Risk + w_u·Urgency − w_d·PathCost(A*)
        </p>
        {view.priorities.length === 0 ? (
          <p className="text-sm text-dim">No eligible person (Waiting and Reachable).</p>
        ) : (
          <ol className="space-y-1.5">
            {view.priorities.map((p, i) => (
              <li
                key={p.person_id}
                className={`rounded border px-2 py-1.5 font-mono text-xs ${
                  p.person_id === view.target ? "border-accent bg-accent/10" : "border-line"
                }`}
              >
                <span className="mr-2 text-dim">#{i + 1}</span>
                {p.breakdown}
                {p.person_id === view.target && <span className="ml-2 text-accent">← target</span>}
              </li>
            ))}
          </ol>
        )}
        <p className="mt-2 text-xs text-dim">
          Simulation values for illustration, not a medical triage rule. The agent switches target
          only when another person beats the current one by more than the margin δ.
        </p>
      </Section>

      <Section
        title="Plan"
        right={view.plan.length > 0 && <Chip tone="accent">cost {fmt(total)}</Chip>}
      >
        {view.plan.length === 0 ? (
          <p className="text-sm text-dim">No plan.</p>
        ) : (
          <ol className="space-y-1">
            {view.plan.map((s) => (
              <li
                key={`${s.label}:${s.params.join(",")}:${s.status}:${s.cost}`}
                className={`flex items-center gap-2 rounded border px-2 py-1.5 text-sm ${
                  s.status === "current"
                    ? "border-accent bg-accent/10"
                    : s.status === "done"
                      ? "border-line text-dim"
                      : "border-line"
                }`}
              >
                <span aria-hidden="true" className="w-4 text-center">
                  {ICON[s.status]}
                </span>
                <span className="sr-only">{s.status}</span>
                <span className="flex-1 font-mono text-xs">{s.label}</span>
                {s.route.length > 0 && (
                  <span className="text-xs text-dim">{s.route.length - 1} moves</span>
                )}
                <span className="w-10 text-right text-xs tabular-nums text-dim">{fmt(s.cost)}</span>
              </li>
            ))}
          </ol>
        )}
        {found && (
          <p className="mt-2 text-xs text-dim">
            Forward state-space A* expanded {String(found.data.expanded)} planning states; Travel
            costs come from A* over the grid.
          </p>
        )}
      </Section>

      {change && (
        <Section
          title={change.is_replan ? "Plan changed" : "Plan adopted"}
          right={change.is_replan && <Btn onClick={() => setExplain("replan")}>Explain replan</Btn>}
        >
          <p className={`text-sm ${change.is_replan ? "text-warn" : "text-dim"}`}>
            <span className="font-semibold">{change.kind.replace("_", " ")}:</span> {change.reason}
          </p>
          {change.is_replan && change.old_steps.length > 0 && (
            <div className="mt-2">
              <div className="text-xs text-dim">Previous plan (dropped)</div>
              <ol className="mt-1 space-y-0.5 font-mono text-xs">
                {change.old_steps.map((s, i) => (
                  <li
                    key={`${s}:${i < change.old_cursor ? "d" : "p"}`}
                    className={i < change.old_cursor ? "text-dim" : "text-bad line-through"}
                  >
                    {i < change.old_cursor ? "✓" : "✗"} {s}
                  </li>
                ))}
              </ol>
            </div>
          )}
        </Section>
      )}

      {view.status === "stuck" && (
        <Section title="Why there is no plan">
          <ul className="space-y-1.5 text-sm">
            {view.no_plan_reasons.map((r) => (
              <li key={r} className="rounded border border-warn/50 bg-warn/5 px-2 py-1.5">
                {r}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-dim">
            The agent never invents a route: each line comes from a failed search or a derived fact.
          </p>
        </Section>
      )}

      <PlannerCompare />

      {view.route.length > 1 && (
        <Section title="Current route">
          <p className="text-sm text-dim">
            {view.route.length - 1} cells to walk, from ({view.route[0]?.join(", ")}) to (
            {view.route.at(-1)?.join(", ")}). Shown as the dashed line on the grid.
          </p>
          <div className="mt-2">
            <Btn onClick={() => setExplain("route")}>Explain this route</Btn>
          </div>
        </Section>
      )}
    </div>
  );
}

/** Forward (progression) vs backward (regression) planning on the same STRIPS problem. */
export function PlannerCompare() {
  const view = useView();
  const sessionId = useSim((s) => s.sessionId);
  const focus = useUi((s) => s.focus);
  const setFocus = useUi((s) => s.setFocus);
  const [scope, setScope] = useState<"target" | "all">("all");
  const run = useMutation({
    mutationFn: (sc: "target" | "all") =>
      api.planCompare({ session_id: sessionId ?? "", tick: view?.tick, scope: sc }),
  });

  // biome-ignore lint/correctness/useExhaustiveDependencies: fire once per focus request
  useEffect(() => {
    if (focus === "planners" && sessionId) {
      setFocus(null);
      run.mutate(scope);
    }
  }, [focus, sessionId]);

  const out = run.data?.tick === view?.tick ? run.data : undefined;
  return (
    <Section title="Forward vs backward planning">
      <div className="flex items-end gap-2">
        <label className="flex-1 text-xs text-dim">
          Goal
          <select
            className="mt-1 w-full rounded-md border border-line bg-raised px-2 py-1.5 text-sm text-ink"
            value={scope}
            onChange={(e) => setScope(e.target.value as "target" | "all")}
          >
            <option value="all">Evacuate everyone eligible</option>
            <option value="target">Evacuate the current target</option>
          </select>
        </label>
        <Btn disabled={run.isPending || !sessionId} onClick={() => run.mutate(scope)}>
          {run.isPending ? "Planning…" : "Compare planners"}
        </Btn>
      </div>
      {run.isError && <p className="mt-2 text-sm text-warn">{run.error.message}</p>}
      {out && (
        <div className="mt-3">
          <p className="font-mono text-xs text-dim">
            goal: {out.goal.join(" ∧ ")} · {out.actions} ground actions
          </p>
          {out.note && <p className="mt-1 text-xs text-warn">{out.note}</p>}
          <table className="mt-2 w-full text-left text-xs">
            <thead className="text-dim">
              <tr>
                <th className="py-1 font-medium">Planner</th>
                <th className="px-1 text-right font-medium">Cost</th>
                <th className="px-1 text-right font-medium">Steps</th>
                <th className="px-1 text-right font-medium">Expanded</th>
                <th className="px-1 text-right font-medium">ms</th>
              </tr>
            </thead>
            <tbody>
              {out.rows.map((r) => (
                <tr key={r.planner} className="border-t border-line" title={r.steps.join(" → ")}>
                  <td className="py-1.5 pr-1">{r.planner}</td>
                  <td className="px-1 text-right tabular-nums">{fmt(r.cost)}</td>
                  <td className="px-1 text-right tabular-nums">{r.found ? r.steps.length : "–"}</td>
                  <td className="px-1 text-right tabular-nums">{r.expanded}</td>
                  <td className="px-1 text-right tabular-nums">{r.time_ms.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-2">
            <Chip tone={out.equal_cost ? "go" : "bad"}>
              {out.equal_cost ? "✓ all planners found the same cost" : "✗ costs differ"}
            </Chip>
          </div>
          {out.rows[0]?.found && (
            <ol className="mt-2 list-decimal space-y-0.5 pl-5 font-mono text-xs text-dim">
              {out.rows[0].steps.map((s, i) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: a plan is an ordered list
                <li key={`${s}-${i}`}>{s}</li>
              ))}
            </ol>
          )}
          <p className="mt-2 text-xs text-dim">
            Forward search expands world states from the start; regression expands sets of sub-goals
            from the goal. Both are optimal here, so their costs must match.
          </p>
        </div>
      )}
    </Section>
  );
}

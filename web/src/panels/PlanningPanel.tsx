import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type TaskNode } from "../api/client";
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
      <Hierarchy />
      <GraphView />

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

type Scope = "target" | "all";

function useScoped<T>(
  focusKey: string,
  call: (b: { session_id: string; tick?: number; scope: Scope }) => Promise<T>,
) {
  const view = useView();
  const sessionId = useSim((s) => s.sessionId);
  const focus = useUi((s) => s.focus);
  const setFocus = useUi((s) => s.setFocus);
  const [scope, setScope] = useState<Scope>("target");
  const run = useMutation({
    mutationFn: (sc: Scope) => call({ session_id: sessionId ?? "", tick: view?.tick, scope: sc }),
  });
  // biome-ignore lint/correctness/useExhaustiveDependencies: fire once per focus request
  useEffect(() => {
    if (focus === focusKey && sessionId) {
      setFocus(null);
      run.mutate(scope);
    }
  }, [focus, sessionId]);
  return { run, scope, setScope, ready: !!sessionId, tick: view?.tick };
}

function ScopeBar({
  scope,
  setScope,
  onRun,
  busy,
  disabled,
  label,
}: {
  scope: Scope;
  setScope: (s: Scope) => void;
  onRun: () => void;
  busy: boolean;
  disabled: boolean;
  label: string;
}) {
  return (
    <div className="flex items-end gap-2">
      <label className="flex-1 text-xs text-dim">
        Goal
        <select
          className="mt-1 w-full rounded-md border border-line bg-raised px-2 py-1.5 text-sm text-ink"
          value={scope}
          onChange={(e) => setScope(e.target.value as Scope)}
        >
          <option value="target">Evacuate the current target</option>
          <option value="all">Evacuate everyone eligible (up to 4)</option>
        </select>
      </label>
      <Btn disabled={busy || disabled} onClick={onRun}>
        {busy ? "Working…" : label}
      </Btn>
    </div>
  );
}

function Task({ node }: { node: TaskNode }) {
  const tone =
    node.kind === "primitive" ? "text-accent" : node.kind === "choice" ? "text-warn" : "text-ink";
  return (
    <li>
      <div className="font-mono text-xs">
        <span className={tone}>{node.task}</span>
        {node.kind === "primitive" && <span className="ml-2 text-dim">cost {fmt(node.cost)}</span>}
        {node.method && <span className="ml-2 text-dim">[{node.method}]</span>}
        {node.note && <span className="ml-2 text-dim">({node.note})</span>}
      </div>
      {node.children.length > 0 && (
        <ul className="ml-3 border-l border-line pl-2">
          {node.children.map((c, i) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: subtasks are an ordered list
            <Task key={`${c.task}-${i}`} node={c} />
          ))}
        </ul>
      )}
    </li>
  );
}

/** HTN: the goal decomposed by methods into primitive actions. */
export function Hierarchy() {
  const { run, scope, setScope, ready, tick } = useScoped("htn", api.htn);
  const out = run.data?.tick === tick ? run.data : undefined;
  return (
    <Section title="Hierarchical plan (HTN)">
      <ScopeBar
        scope={scope}
        setScope={setScope}
        onRun={() => run.mutate(scope)}
        busy={run.isPending}
        disabled={!ready}
        label="Decompose"
      />
      {run.isError && <p className="mt-2 text-sm text-warn">{run.error.message}</p>}
      {out && (
        <div className="mt-3">
          {!out.found && <p className="mb-2 text-sm text-warn">No decomposition: {out.reason}</p>}
          <ul>
            <Task node={out.tree} />
          </ul>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Chip tone="accent">HTN cost {fmt(out.cost)}</Chip>
            <Chip>optimal planner {fmt(out.optimal_cost)}</Chip>
            {out.found && out.optimal_cost !== null && out.optimal_cost !== undefined && (
              <Chip tone={out.cost - out.optimal_cost < 1e-9 ? "go" : "warn"}>
                {out.cost - out.optimal_cost < 1e-9
                  ? "✓ matches the optimum"
                  : `+${fmt(out.cost - out.optimal_cost)} vs optimum`}
              </Chip>
            )}
          </div>
          <p className="mt-2 text-xs text-dim">
            Compound tasks are white, primitive actions cyan, choices yellow. Methods encode how a
            rescue is done, so there is no search over orderings: fast and readable, but only as
            good as the methods.
          </p>
        </div>
      )}
    </Section>
  );
}

/** Planning graph: proposition and action levels with mutex links. */
export function GraphView() {
  const { run, scope, setScope, ready, tick } = useScoped("graph", api.planGraph);
  const [open, setOpen] = useState<number | null>(null);
  const out = run.data?.tick === tick ? run.data : undefined;
  return (
    <Section
      help="Each level adds everything one more round of actions could make true. Mutex (⊗) marks pairs that cannot hold or happen together. The first level where the goal appears without a mutex is a lower bound on the plan's length."
      title="Planning graph"
    >
      <ScopeBar
        scope={scope}
        setScope={setScope}
        onRun={() => run.mutate(scope)}
        busy={run.isPending}
        disabled={!ready}
        label="Build graph"
      />
      {run.isError && <p className="mt-2 text-sm text-warn">{run.error.message}</p>}
      {out && (
        <div className="mt-3">
          <div className="mb-2 flex flex-wrap gap-1.5">
            <Chip tone={out.goal_level === null || out.goal_level === undefined ? "bad" : "accent"}>
              {out.goal_level === null || out.goal_level === undefined
                ? "goal never appears: no plan"
                : `goal first possible at level ${out.goal_level}`}
            </Chip>
            {out.plan_steps !== null && out.plan_steps !== undefined && (
              <Chip>optimal plan: {out.plan_steps} steps</Chip>
            )}
            {out.leveled_off && <Chip>leveled off</Chip>}
          </div>
          <ol className="space-y-1">
            {out.levels.map((lv) => {
              const real = lv.actions.filter((a) => !a.startsWith("keep "));
              const hasGoal = out.goal.every((g) => lv.atoms.includes(g));
              return (
                <li key={lv.index} className="rounded border border-line">
                  <button
                    type="button"
                    className="flex w-full items-center gap-2 px-2 py-1 text-left text-xs hover:bg-raised"
                    aria-expanded={open === lv.index}
                    onClick={() => setOpen(open === lv.index ? null : lv.index)}
                  >
                    <span className="w-8 font-semibold text-accent">S{lv.index}</span>
                    <span className="flex-1">
                      {lv.atoms.length} atoms, {lv.atom_mutex.length} mutex
                      {lv.actions.length > 0 &&
                        ` · A${lv.index}: ${real.length} actions + ${lv.actions.length - real.length} no-ops, ${lv.action_mutex.length} mutex`}
                    </span>
                    {hasGoal && (
                      <Chip tone={lv.index >= (out.goal_level ?? 99) ? "go" : "warn"}>goal</Chip>
                    )}
                  </button>
                  {open === lv.index && (
                    <div className="space-y-1 border-t border-line px-2 py-1.5 font-mono text-[11px]">
                      <div>
                        <span className="text-dim">atoms: </span>
                        {lv.atoms.join("  ")}
                      </div>
                      {lv.atom_mutex.length > 0 && (
                        <div>
                          <span className="text-dim">atom mutex: </span>
                          {lv.atom_mutex.map(([a, b]) => `${a} ⊗ ${b}`).join("  ")}
                        </div>
                      )}
                      {real.length > 0 && (
                        <div>
                          <span className="text-dim">actions: </span>
                          {real.join("  ")}
                        </div>
                      )}
                      {lv.action_mutex.length > 0 && (
                        <div>
                          <span className="text-dim">
                            action mutex ({lv.action_mutex.length}), first 12:{" "}
                          </span>
                          {lv.action_mutex
                            .slice(0, 12)
                            .map(([a, b]) => `${a} ⊗ ${b}`)
                            .join("  ")}
                        </div>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
          </ol>
        </div>
      )}
    </Section>
  );
}

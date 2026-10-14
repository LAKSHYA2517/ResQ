import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type Cell } from "../api/client";
import { Lines } from "../components/Chart";
import { Btn, Chip, Empty, fmt, Section } from "../components/ui";
import { useSim, useView } from "../store/sim";
import { useUi } from "../store/ui";

const INPUT = "mt-1 w-full rounded-md border border-line bg-raised px-2 py-1.5 text-sm text-ink";
const METHOD: Record<string, string> = {
  greedy: "Greedy by priority",
  hill_climbing: "Hill climbing (restarts)",
  simulated_annealing: "Simulated annealing",
  genetic: "Genetic algorithm",
  exhaustive: "Exhaustive optimum",
};

function OrderOptimizer() {
  const view = useView();
  const sessionId = useSim((s) => s.sessionId);
  const focus = useUi((s) => s.focus);
  const setFocus = useUi((s) => s.setFocus);
  const [seed, setSeed] = useState(1);
  const [steps, setSteps] = useState(600);
  const [gens, setGens] = useState(60);
  const run = useMutation({
    mutationFn: () =>
      api.order({
        session_id: sessionId ?? "",
        tick: view?.tick,
        seed,
        sa_steps: steps,
        ga_generations: gens,
      }),
  });

  // biome-ignore lint/correctness/useExhaustiveDependencies: fire once per focus request
  useEffect(() => {
    if (focus === "order" && sessionId) {
      setFocus(null);
      run.mutate();
    }
  }, [focus, sessionId]);

  const out = run.data?.tick === view?.tick ? run.data : undefined;
  const curves = out?.rows.filter((r) => r.curve.length > 1) ?? [];
  return (
    <Section title="Rescue-order optimizer (local search)">
      <p className="mb-2 text-sm text-dim">
        Minimise Σ weight × completion time over the order of rescues, where weight = w_r·Risk +
        w_u·Urgency and every leg is a real A* cost.
      </p>
      <div className="flex items-end gap-2 text-xs text-dim">
        <label className="w-16">
          Seed
          <input
            type="number"
            className={INPUT}
            value={seed}
            onChange={(e) => setSeed(Math.round(Number(e.target.value) || 0))}
          />
        </label>
        <label className="flex-1">
          SA steps
          <input
            type="number"
            min={1}
            className={INPUT}
            value={steps}
            onChange={(e) => setSteps(Math.max(1, Number(e.target.value) || 1))}
          />
        </label>
        <label className="flex-1">
          GA generations
          <input
            type="number"
            min={1}
            className={INPUT}
            value={gens}
            onChange={(e) => setGens(Math.max(1, Number(e.target.value) || 1))}
          />
        </label>
        <Btn tone="primary" disabled={run.isPending || !sessionId} onClick={() => run.mutate()}>
          {run.isPending ? "Optimising…" : "Optimise"}
        </Btn>
      </div>
      {run.isError && <p className="mt-2 text-sm text-bad">{run.error.message}</p>}
      {out && (
        <div className="mt-3">
          {out.people.length === 0 ? (
            <p className="text-sm text-warn">
              Nobody can be scheduled: {out.skipped.join("; ") || "no one is waiting"}.
            </p>
          ) : (
            <>
              <p className="font-mono text-xs text-dim">
                {out.people.map((p) => `${p.id}(w=${fmt(p.weight)}→${p.exit})`).join("  ")}
              </p>
              {out.skipped.length > 0 && (
                <p className="mt-1 text-xs text-warn">Left out: {out.skipped.join("; ")}</p>
              )}
              <table className="mt-2 w-full text-left text-xs">
                <thead className="text-dim">
                  <tr>
                    <th className="py-1 font-medium">Method</th>
                    <th className="px-1 text-right font-medium">Cost</th>
                    <th className="px-1 text-right font-medium">Gap</th>
                    <th className="px-1 text-right font-medium">Evals</th>
                  </tr>
                </thead>
                <tbody>
                  {out.rows.map((r) => (
                    <tr key={r.method} className="border-t border-line align-top">
                      <td className="py-1.5">
                        {METHOD[r.method] ?? r.method}
                        <div className="font-mono text-[11px] text-dim">{r.order.join(" → ")}</div>
                      </td>
                      <td className="px-1 text-right tabular-nums">{fmt(r.cost)}</td>
                      <td className="px-1 text-right whitespace-nowrap">
                        {r.gap === null || r.gap === undefined ? (
                          "–"
                        ) : r.gap < 1e-9 ? (
                          <Chip tone="go">✓ optimal</Chip>
                        ) : (
                          <Chip tone="warn">+{fmt(r.gap)}</Chip>
                        )}
                      </td>
                      <td className="px-1 text-right tabular-nums">{r.evaluations}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {curves.length > 0 && (
                <div className="mt-3">
                  <Lines
                    series={curves.map((r) => ({
                      name: METHOD[r.method] ?? r.method,
                      points: r.curve.map((y, x) => ({ x, y })),
                    }))}
                    xLabel="iteration / generation"
                    yLabel="best cost so far"
                    reference={out.optimum ?? undefined}
                    referenceLabel="optimum"
                  />
                </div>
              )}
              <p className="mt-1 text-xs text-dim">
                {out.optimum === null || out.optimum === undefined
                  ? "More than 7 people: too many orders to enumerate, so no optimum line."
                  : "The optimum comes from trying every order; no local search can beat it."}
              </p>
            </>
          )}
        </div>
      )}
    </Section>
  );
}

function Adversarial() {
  const view = useView();
  const { sessionId, scenarioId, fireMode, start, setHighlight, busy } = useSim();
  const focus = useUi((s) => s.focus);
  const setFocus = useUi((s) => s.setFocus);
  const [depth, setDepth] = useState(4);
  const [k, setK] = useState(1);
  const run = useMutation({
    mutationFn: () => api.adversarial({ session_id: sessionId ?? "", tick: view?.tick, depth, k }),
    onSuccess: (d) => setHighlight(d.alphabeta.line.flat() as Cell[]),
  });

  // biome-ignore lint/correctness/useExhaustiveDependencies: fire once per focus request
  useEffect(() => {
    if (focus === "adversarial" && sessionId) {
      setFocus(null);
      run.mutate();
    }
  }, [focus, sessionId]);

  const out = run.data?.tick === view?.tick ? run.data : undefined;
  const adversarial = fireMode === "adversarial";
  return (
    <Section
      title="Adversarial fire (minimax, alpha-beta)"
      right={
        <Chip tone={adversarial ? "bad" : "default"}>
          {adversarial ? "worst-case fire" : "random fire"}
        </Chip>
      }
    >
      <p className="mb-2 text-sm text-dim">
        A two-player zero-sum game: the agent (MIN) wants to finish its current leg cheaply, the
        fire (MAX) ignites cells to make that as costly as possible.
      </p>
      <div className="flex items-end gap-2 text-xs text-dim">
        <label className="flex-1">
          Depth (plies)
          <input
            type="number"
            min={1}
            max={6}
            className={INPUT}
            value={depth}
            onChange={(e) => setDepth(Math.min(6, Math.max(1, Number(e.target.value) || 1)))}
          />
        </label>
        <label className="flex-1">
          Ignitions / turn
          <input
            type="number"
            min={1}
            max={2}
            className={INPUT}
            value={k}
            onChange={(e) => setK(Math.min(2, Math.max(1, Number(e.target.value) || 1)))}
          />
        </label>
        <Btn tone="primary" disabled={run.isPending || !sessionId} onClick={() => run.mutate()}>
          {run.isPending ? "Searching…" : "Analyse this move"}
        </Btn>
      </div>
      {run.isError && <p className="mt-2 text-sm text-warn">{run.error.message}</p>}
      {out && (
        <div className="mt-3">
          <table className="w-full text-left text-xs">
            <thead className="text-dim">
              <tr>
                <th className="py-1 font-medium">Algorithm</th>
                <th className="px-1 font-medium">Best step</th>
                <th className="px-1 text-right font-medium">Value</th>
                <th className="px-1 text-right font-medium">Nodes</th>
                <th className="px-1 text-right font-medium">Pruned</th>
              </tr>
            </thead>
            <tbody>
              {[out.minimax, out.alphabeta].map((g) => (
                <tr key={g.algorithm} className="border-t border-line">
                  <td className="py-1.5">{g.algorithm === "minimax" ? "Minimax" : "Alpha-beta"}</td>
                  <td className="px-1 font-mono">{g.move ? `(${g.move.join(", ")})` : "none"}</td>
                  <td className="px-1 text-right tabular-nums">
                    {g.cut_off ? "∞ cut off" : fmt(g.value)}
                  </td>
                  <td className="px-1 text-right tabular-nums">{g.nodes}</td>
                  <td className="px-1 text-right tabular-nums">{g.cutoffs}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Chip tone={out.same_move && out.same_value ? "go" : "bad"}>
              {out.same_move && out.same_value ? "✓ same move and value" : "✗ results differ"}
            </Chip>
            <Chip tone="accent">
              {out.nodes_saved} nodes saved (
              {Math.round((100 * out.nodes_saved) / Math.max(1, out.minimax.nodes))}%)
            </Chip>
            <Chip>calm cost {fmt(out.calm_cost)}</Chip>
          </div>
          <p className="mt-2 text-xs text-dim">
            Best line (highlighted on the grid):{" "}
            {out.alphabeta.line
              .map(
                (m, i) =>
                  `${i % 2 === 0 ? "agent" : "fire"} ${m.map((c) => `(${c.join(",")})`).join("+") || "passes"}`,
              )
              .join(" → ")}
          </p>
        </div>
      )}
      <div className="mt-3 border-t border-line pt-3">
        <p className="mb-2 text-xs text-dim">
          Mode for the whole run: in worst-case mode the fire stops spreading at random and instead
          lights the cell alpha-beta picks against the agent each tick. Switching restarts the
          scenario.
        </p>
        <Btn
          tone={adversarial ? "default" : "danger"}
          disabled={busy || !scenarioId}
          onClick={() =>
            scenarioId &&
            void start(scenarioId, undefined, adversarial ? "stochastic" : "adversarial")
          }
        >
          {adversarial ? "Restart with random fire" : "Restart with worst-case fire"}
        </Btn>
      </div>
    </Section>
  );
}

export function OptimizePanel() {
  const view = useView();
  if (!view)
    return <Empty>Start a scenario to optimise the rescue order or play the fire game.</Empty>;
  return (
    <div className="h-full overflow-y-auto">
      <OrderOptimizer />
      <Adversarial />
    </div>
  );
}

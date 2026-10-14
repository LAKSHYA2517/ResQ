import { useMutation } from "@tanstack/react-query";
import { useEffect } from "react";
import { api } from "../api/client";
import { Btn, Chip, fmt, Section } from "../components/ui";
import { useUi } from "../store/ui";

const NAMES: Record<string, string> = {
  reflex: "Simple reflex",
  goal: "Goal-based",
  utility: "Utility-based (ResQ)",
};

/** Module 1 benchmark: three kinds of agent on identical seeded scenarios. */
export function Benchmark() {
  const focus = useUi((s) => s.focus);
  const setFocus = useUi((s) => s.setFocus);
  const run = useMutation({ mutationFn: () => api.bench({ random: 20, seed: 1 }) });

  // biome-ignore lint/correctness/useExhaustiveDependencies: fire once per focus request
  useEffect(() => {
    if (focus === "bench") {
      setFocus(null);
      run.mutate();
    }
  }, [focus]);

  const out = run.data;
  const scenarios = out ? [...new Set(out.rows.map((r) => r.scenario))] : [];
  return (
    <Section
      title="Agent-type benchmark"
      right={
        <Btn tone="primary" disabled={run.isPending} onClick={() => run.mutate()}>
          {run.isPending ? "Running…" : "Run benchmark"}
        </Btn>
      }
    >
      <p className="text-sm text-dim">
        Reflex (percept → action, no map), goal-based (A* to the nearest person) and the full
        utility-based agent on every predefined scenario plus 20 seeded random ones.
      </p>
      {run.isError && <p className="mt-2 text-sm text-bad">{run.error.message}</p>}
      {out && (
        <div className="mt-3">
          <div className="space-y-1.5">
            {out.summaries.map((s) => (
              <div key={s.agent} className="text-xs">
                <div className="flex justify-between">
                  <span className="font-semibold">{NAMES[s.agent] ?? s.agent}</span>
                  <span className="tabular-nums">
                    {s.rescued}/{s.people} rescued ({s.rescued_pct.toFixed(1)}%)
                  </span>
                </div>
                <div className="h-3 rounded bg-bg">
                  <div className="h-3 rounded bg-accent" style={{ width: `${s.rescued_pct}%` }} />
                </div>
                <div className="text-dim">
                  mean cost {fmt(s.mean_cost)} · mean ticks {fmt(s.mean_ticks)} · cost per rescue{" "}
                  {fmt(s.cost_per_rescue)} · replans {s.replans}
                </div>
              </div>
            ))}
          </div>
          <div className="mt-2">
            <Chip tone={out.expected_order_holds ? "go" : "warn"}>
              {out.expected_order_holds
                ? "✓ utility ≥ goal-based ≥ reflex in people rescued"
                : "✗ the expected order does not hold on this set"}
            </Chip>
          </div>
          <details className="mt-2">
            <summary className="cursor-pointer text-xs text-accent">
              Per scenario ({scenarios.length}): rescued · cost
            </summary>
            <table className="mt-1 w-full text-left text-[11px]">
              <thead className="text-dim">
                <tr>
                  <th className="py-1 font-medium">Scenario</th>
                  <th className="px-1 font-medium">Reflex</th>
                  <th className="px-1 font-medium">Goal</th>
                  <th className="px-1 font-medium">Utility</th>
                </tr>
              </thead>
              <tbody>
                {scenarios.map((name) => (
                  <tr key={name} className="border-t border-line">
                    <td className="py-1">{name}</td>
                    {["reflex", "goal", "utility"].map((kind) => {
                      const r = out.rows.find((x) => x.scenario === name && x.agent === kind);
                      return (
                        <td key={kind} className="px-1 tabular-nums">
                          {r ? `${r.rescued}/${r.people} · ${fmt(r.cost)}` : "–"}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
          <p className="mt-2 text-xs text-dim">
            The utility agent goes for the person most at risk first, which can cost more path than
            taking the nearest: a higher cost beside more rescues is that trade-off.
          </p>
        </div>
      )}
    </Section>
  );
}

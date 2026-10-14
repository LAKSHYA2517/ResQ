import { useQuery } from "@tanstack/react-query";
import { api, type Cell } from "../api/client";
import { Empty, Section } from "../components/ui";
import { cellsIn } from "../lib/cells";
import { useSim, useView } from "../store/sim";
import { useUi } from "../store/ui";
import { ProveIt } from "./ProveIt";

function predicate(fact: string) {
  return fact.slice(0, fact.indexOf("("));
}

export function ReasoningPanel() {
  const view = useView();
  const lastEvent = useSim((s) => s.lastEvent);
  const highlight = useSim((s) => s.highlight);
  const setHighlight = useSim((s) => s.setHighlight);
  const showState = useUi((s) => s.showState);
  const setShowState = useUi((s) => s.setShowState);
  const rules = useQuery({ queryKey: ["rules"], queryFn: api.rules, staleTime: Infinity });
  if (!view) return <Empty>Start a scenario to see what the agent knows.</Empty>;

  const diff = lastEvent && lastEvent.snapshot.tick === view.tick ? lastEvent.diff : null;
  const byRule = new Map<string, number>();
  for (const dv of view.derived) byRule.set(dv.rule, (byRule.get(dv.rule) ?? 0) + 1);

  const groups = new Map<string, string[]>();
  for (const f of view.facts) {
    const p = predicate(f);
    groups.set(p, [...(groups.get(p) ?? []), f]);
  }

  const passes = [...new Set(view.derived.map((dv) => dv.iteration))].sort((a, b) => a - b);
  const toggle = (cells: Cell[]) => {
    const same =
      highlight.length === cells.length && cells.every((c, i) => c.join() === highlight[i]?.join());
    setHighlight(same ? [] : cells);
  };

  const { terrain, ...rest } = view.state;

  return (
    <div className="h-full overflow-y-auto">
      {diff && (
        <Section title="Last event changed the knowledge base">
          {diff.added.length + diff.removed.length === 0 ? (
            <p className="text-sm text-dim">No facts changed.</p>
          ) : (
            <ul className="space-y-0.5 font-mono text-xs">
              {diff.added.map((f) => (
                <li key={`+${f}`} className="text-go">
                  + {f}
                </li>
              ))}
              {diff.removed.map((f) => (
                <li key={`-${f}`} className="text-bad">
                  − {f}
                </li>
              ))}
            </ul>
          )}
          {lastEvent?.replan_reason && (
            <p className="mt-2 text-sm text-warn">Replan reason: {lastEvent.replan_reason}</p>
          )}
        </Section>
      )}

      <ProveIt />

      <Section
        title="World state (structured data)"
        right={
          <button
            type="button"
            className="text-xs text-accent hover:underline"
            onClick={() => setShowState(!showState)}
          >
            {showState ? "hide" : "show"}
          </button>
        }
      >
        {showState ? (
          <pre className="max-h-64 overflow-auto rounded-md bg-bg p-2 font-mono text-xs leading-snug text-dim">
            {JSON.stringify(
              { ...rest, terrain: terrain.map((row) => row.map((t) => t[0]).join("")) },
              null,
              1,
            )}
          </pre>
        ) : (
          <p className="text-sm text-dim">
            Tick {view.state.tick}, {view.state.rows}×{view.state.cols} grid,{" "}
            {view.state.people.length} people, {view.state.fire.length} fire cell(s),{" "}
            {view.state.hot.length} hot.
          </p>
        )}
      </Section>

      <Section title={`Base facts (${view.facts.length} shown of ${view.metrics.kb_base})`}>
        <div className="space-y-2 font-mono text-xs">
          {[...groups].map(([pred, facts]) => (
            <div key={pred}>
              <div className="text-dim">
                {pred} <span className="text-line">×{view.fact_counts[pred] ?? facts.length}</span>
              </div>
              <div className="flex flex-wrap gap-x-3 gap-y-0.5">
                {facts.map((f) => (
                  <button
                    key={f}
                    type="button"
                    className="text-left text-ink hover:text-accent"
                    onClick={() => toggle(cellsIn(f))}
                  >
                    {f}
                  </button>
                ))}
              </div>
            </div>
          ))}
          {view.fact_counts.Adjacent !== undefined && (
            <div className="text-dim">
              Adjacent ×{view.fact_counts.Adjacent} (grid geometry, not listed)
            </div>
          )}
        </div>
      </Section>

      <Section
        help="Closed world: anything not known or derivable is false. The number is how many facts the rule derived this tick."
        title={`Rules (${rules.data?.length ?? "…"})`}
      >
        {rules.isError && <p className="text-sm text-bad">Could not load rules.</p>}
        <ul className="space-y-1 font-mono text-xs">
          {rules.data?.map((r) => (
            <li key={r.name} className="flex items-baseline justify-between gap-2">
              <span>
                <span className="text-dim">{r.name}: </span>
                {r.text}
              </span>
              <span className={byRule.get(r.name) ? "text-go" : "text-dim"}>
                {byRule.get(r.name) ?? 0}
              </span>
            </li>
          ))}
        </ul>
      </Section>

      <Section title={`Derived facts (${view.derived.length}) with provenance`}>
        {view.derived.length === 0 && <p className="text-sm text-dim">Nothing derived.</p>}
        {passes.map((pass) => (
          <div key={pass} className="mb-3">
            <div className="mb-1 text-xs text-dim">Forward-chaining pass {pass}</div>
            <ul className="space-y-1.5">
              {view.derived
                .filter((dv) => dv.iteration === pass)
                .map((dv) => (
                  <li key={dv.fact}>
                    <button
                      type="button"
                      className="block w-full rounded border border-line bg-raised px-2 py-1 text-left hover:border-accent"
                      onClick={() => toggle(cellsIn(`${dv.fact} ${dv.premises.join(" ")}`))}
                    >
                      <span className="font-mono text-sm text-go">{dv.fact}</span>
                      <span className="ml-2 text-xs text-dim">by {dv.rule}</span>
                      <span className="block font-mono text-xs text-dim">
                        {dv.premises.join("  &  ")}
                      </span>
                      <span className="block font-mono text-xs text-line">
                        {Object.entries(dv.bindings)
                          .map(([k, v]) => `${k}=${v}`)
                          .join(", ")}
                      </span>
                    </button>
                  </li>
                ))}
            </ul>
          </div>
        ))}
      </Section>
    </div>
  );
}

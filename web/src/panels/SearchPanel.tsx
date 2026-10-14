import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { type AlgorithmName, api, type HeuristicName } from "../api/client";
import { RaceDialog } from "../components/RaceDialog";
import { Btn, Chip, Empty, fmt, Section } from "../components/ui";
import { eventsOf, keyed } from "../lib/trace";
import { useSim, useView } from "../store/sim";
import { useUi } from "../store/ui";

const ALGORITHMS: { id: AlgorithmName; label: string; informed: boolean }[] = [
  { id: "bfs", label: "BFS", informed: false },
  { id: "dfs", label: "DFS", informed: false },
  { id: "dls", label: "DLS (depth-limited)", informed: false },
  { id: "iddfs", label: "IDDFS", informed: false },
  { id: "ucs", label: "UCS", informed: false },
  { id: "greedy", label: "Greedy best-first", informed: true },
  { id: "astar", label: "A*", informed: true },
  { id: "weighted_astar", label: "Weighted A*", informed: true },
];
const HEURISTICS: HeuristicName[] = ["manhattan", "euclidean", "zero", "weighted"];
const INPUT = "mt-1 w-full rounded-md border border-line bg-raised px-2 py-1.5 text-sm text-ink";

export const short = (label: string) => label.replace("astar", "A*").replace("+", " · ");

export function SearchPanel() {
  const view = useView();
  const sessionId = useSim((s) => s.sessionId);
  const setHighlight = useSim((s) => s.setHighlight);
  const overlay = useUi((s) => s.overlay);
  const setOverlay = useUi((s) => s.setOverlay);
  const compare = useUi((s) => s.compare);
  const setCompare = useUi((s) => s.setCompare);
  const focus = useUi((s) => s.focus);
  const setFocus = useUi((s) => s.setFocus);
  const [picked, setPicked] = useState<AlgorithmName[]>(["bfs", "dfs", "ucs", "greedy", "astar"]);
  const [heuristic, setHeuristic] = useState<HeuristicName>("manhattan");
  const [limit, setLimit] = useState(20);
  const [w, setW] = useState(2);
  const [target, setTarget] = useState("");
  const [racing, setRacing] = useState(false);
  const [labH, setLabH] = useState<HeuristicName>("weighted");

  const run = useMutation({
    mutationFn: (race: boolean) =>
      api
        .compare({
          session_id: sessionId ?? "",
          tick: view?.tick,
          target: chosen || undefined,
          limit,
          w,
          runs: ALGORITHMS.filter((a) => picked.includes(a.id)).map((a) => ({
            algorithm: a.id,
            heuristic: a.informed ? heuristic : null,
          })),
        })
        .then((data) => ({ data, race })),
    onSuccess: ({ data, race }) => {
      setCompare(data);
      setOverlay(null);
      setRacing(race);
    },
  });
  const lab = useMutation({
    mutationFn: () =>
      api.heuristicCheck({
        session_id: sessionId ?? "",
        tick: view?.tick,
        target: chosen || undefined,
        heuristic: labH,
        w,
      }),
  });

  const waiting = view?.state.people.filter((p) => p.status === "WAITING") ?? [];
  const chosen = target || view?.target || waiting[0]?.id || "";

  // The Syllabus "Run it" links open the race directly.
  // biome-ignore lint/correctness/useExhaustiveDependencies: fire once per focus request
  useEffect(() => {
    if (focus === "race" && sessionId && waiting.length > 0) {
      setFocus(null);
      run.mutate(true);
    }
  }, [focus, sessionId]);

  if (!view || !sessionId) return <Empty>Start a scenario to compare search algorithms.</Empty>;
  const result = compare?.tick === view.tick ? compare : undefined;
  const maxExpanded = Math.max(1, ...(result?.runs.map((r) => r.expanded) ?? [1]));
  const searches = eventsOf(view, "RouteComputed");
  const none = waiting.length === 0;

  return (
    <div className="h-full overflow-y-auto">
      <Section title="Compare algorithms on one problem">
        <p className="mb-2 text-sm text-dim">
          Agent at ({view.state.agent.pos.join(", ")}) → a waiting person, tick {view.tick}.
        </p>
        <label className="mb-2 block text-xs text-dim">
          Target
          <select className={INPUT} value={chosen} onChange={(e) => setTarget(e.target.value)}>
            {waiting.map((p) => (
              <option key={p.id} value={p.id}>
                {p.id} at ({p.pos.join(", ")})
              </option>
            ))}
          </select>
        </label>
        <div className="mb-2 grid grid-cols-2 gap-x-3 gap-y-1">
          {ALGORITHMS.map((a) => (
            <label key={a.id} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={picked.includes(a.id)}
                onChange={(e) =>
                  setPicked(e.target.checked ? [...picked, a.id] : picked.filter((p) => p !== a.id))
                }
              />
              {a.label}
            </label>
          ))}
        </div>
        <div className="mb-3 grid grid-cols-3 gap-2 text-xs text-dim">
          <label>
            Heuristic
            <select
              className={INPUT}
              value={heuristic}
              onChange={(e) => setHeuristic(e.target.value as HeuristicName)}
            >
              {HEURISTICS.map((h) => (
                <option key={h}>{h}</option>
              ))}
            </select>
          </label>
          <label>
            DLS limit
            <input
              type="number"
              min={0}
              className={INPUT}
              value={limit}
              onChange={(e) => setLimit(Math.max(0, Number(e.target.value) || 0))}
            />
          </label>
          <label>
            Weight w
            <input
              type="number"
              min={0}
              step={0.5}
              className={INPUT}
              value={w}
              onChange={(e) => setW(Math.max(0, Number(e.target.value) || 0))}
            />
          </label>
        </div>
        <div className="flex gap-2">
          <Btn
            tone="primary"
            disabled={run.isPending || picked.length === 0 || none}
            onClick={() => run.mutate(false)}
          >
            {run.isPending ? "Searching…" : "Run comparison"}
          </Btn>
          <Btn
            disabled={run.isPending || picked.length === 0 || none}
            onClick={() => run.mutate(true)}
          >
            Race
          </Btn>
        </div>
        {none && <p className="mt-2 text-sm text-dim">Nobody is waiting at this tick.</p>}
        {run.isError && <p className="mt-2 text-sm text-bad">{run.error.message}</p>}
      </Section>

      {result && (
        <Section
          help='"vs UCS" compares each path cost with a reference uniform-cost run; it is computed, not assumed. Click a row to paint its explored cells and path on the grid (blue = expanded early, amber = late). IDDFS counts the repeated work of every pass.'
          title={`Results: ${result.target_id} at (${result.goal.join(", ")})`}
          right={<Btn onClick={() => setRacing(true)}>Replay race</Btn>}
        >
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-dim">
                <tr>
                  <th className="py-1 pr-2 font-medium">Algorithm</th>
                  <th className="px-1 text-right font-medium">Cost</th>
                  <th className="px-1 text-right font-medium">Steps</th>
                  <th className="px-1 text-right font-medium">Expanded</th>
                  <th className="px-1 text-right font-medium">Front.</th>
                  <th className="pl-2 font-medium">vs UCS</th>
                </tr>
              </thead>
              <tbody>
                {result.runs.map((r) => (
                  <tr
                    key={r.label}
                    className={`cursor-pointer border-t border-line hover:bg-raised ${
                      overlay?.label === r.label ? "bg-raised" : ""
                    }`}
                    onClick={() =>
                      setOverlay(
                        overlay?.label === r.label
                          ? null
                          : { label: r.label, explored: r.expansion_order, path: r.path },
                      )
                    }
                  >
                    <td className="py-1.5 pr-2 font-medium" title={r.reason}>
                      {short(r.label)}
                    </td>
                    <td className="px-1 text-right tabular-nums">{fmt(r.cost)}</td>
                    <td className="px-1 text-right tabular-nums">{r.found ? r.steps : "–"}</td>
                    <td className="px-1 text-right tabular-nums">{r.expanded}</td>
                    <td className="px-1 text-right tabular-nums">{r.max_frontier}</td>
                    <td className="pl-2 whitespace-nowrap">
                      {!r.found ? (
                        <Chip tone="bad">
                          {r.reason.startsWith("cutoff") ? "cutoff" : "no route"}
                        </Chip>
                      ) : r.optimal_vs_ucs ? (
                        <Chip tone="go">✓ optimal</Chip>
                      ) : (
                        <Chip tone="warn">✗ costlier</Chip>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-3 space-y-1">
            <div className="text-xs text-dim">Nodes expanded</div>
            {result.runs.map((r) => (
              <div key={r.label} className="flex items-center gap-2 text-xs">
                <span className="w-32 shrink-0 truncate">{short(r.label)}</span>
                <div className="h-3 flex-1 rounded bg-bg">
                  <div
                    className="h-3 rounded bg-accent"
                    style={{ width: `${(r.expanded / maxExpanded) * 100}%` }}
                  />
                </div>
                <span className="w-9 text-right tabular-nums">{r.expanded}</span>
              </div>
            ))}
          </div>
        </Section>
      )}

      <Section
        help="Checks h(n) ≤ true cost (admissible) and h(n) ≤ c(n, n′) + h(n′) (consistent) on every passable cell, then runs A* with it."
        title="Heuristic lab"
      >
        <div className="flex items-end gap-2">
          <label className="flex-1 text-xs text-dim">
            Heuristic (weight w = {w})
            <select
              className={INPUT}
              value={labH}
              onChange={(e) => setLabH(e.target.value as HeuristicName)}
            >
              {HEURISTICS.map((h) => (
                <option key={h}>{h}</option>
              ))}
            </select>
          </label>
          <Btn disabled={lab.isPending || none} onClick={() => lab.mutate()}>
            Check
          </Btn>
        </div>
        {lab.isError && <p className="mt-2 text-sm text-bad">{lab.error.message}</p>}
        {lab.data && (
          <div className="mt-3 text-sm">
            <div className="flex flex-wrap gap-1.5">
              <Chip tone={lab.data.admissible ? "go" : "bad"}>
                {lab.data.admissible
                  ? "✓ admissible"
                  : `✗ not admissible (${lab.data.n_admissibility_violations} cells)`}
              </Chip>
              <Chip tone={lab.data.consistent ? "go" : "bad"}>
                {lab.data.consistent
                  ? "✓ consistent"
                  : `✗ not consistent (${lab.data.n_consistency_violations} edges)`}
              </Chip>
              <Chip tone={lab.data.astar.optimal_vs_ucs ? "go" : "warn"}>
                A* cost {fmt(lab.data.astar.cost)}, {lab.data.astar.expanded} expanded,{" "}
                {lab.data.astar.optimal_vs_ucs ? "optimal" : "not optimal"}
              </Chip>
            </div>
            {lab.data.admissibility_violations.length > 0 && (
              <>
                <div className="mt-2 text-xs text-dim">
                  Overestimates (h &gt; true cost), first {lab.data.admissibility_violations.length}
                  :
                </div>
                <ul className="mt-1 max-h-28 overflow-y-auto font-mono text-xs">
                  {lab.data.admissibility_violations.map((v) => (
                    <li key={v.cell.join()}>
                      <button
                        type="button"
                        className="hover:text-accent"
                        onClick={() => setHighlight([v.cell])}
                      >
                        ({v.cell.join(", ")}): h = {fmt(v.h)} &gt; {fmt(v.true_cost)}
                      </button>
                    </li>
                  ))}
                </ul>
                <Btn
                  className="mt-2"
                  onClick={() => setHighlight(lab.data.admissibility_violations.map((v) => v.cell))}
                >
                  Show them on the grid
                </Btn>
              </>
            )}
          </div>
        )}
      </Section>

      <Section title="Searches the agent ran this tick">
        {searches.length === 0 ? (
          <p className="text-sm text-dim">None: the agent kept following its plan.</p>
        ) : (
          <ul className="space-y-1 font-mono text-xs text-dim">
            {keyed(searches).map((l) => (
              <li key={l.key}>{l.text}</li>
            ))}
          </ul>
        )}
        <p className="mt-2 text-xs text-dim">
          Total so far: {view.metrics.searches} A* runs, {view.metrics.nodes_expanded} cells
          expanded.
        </p>
      </Section>

      {racing && result && (
        <RaceDialog result={result} state={view.state} onClose={() => setRacing(false)} />
      )}
    </div>
  );
}

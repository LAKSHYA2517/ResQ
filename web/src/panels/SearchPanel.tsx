import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api, type RunSpec } from "../api/client";
import { Btn, Chip, Empty, fmt, Section } from "../components/ui";
import { eventsOf, keyed } from "../lib/trace";
import { useSim, useView } from "../store/sim";
import { useUi } from "../store/ui";

const CHOICES: { id: string; label: string; spec: RunSpec }[] = [
  { id: "bfs", label: "BFS", spec: { algorithm: "bfs" } },
  { id: "ucs", label: "UCS", spec: { algorithm: "ucs" } },
  {
    id: "astar+manhattan",
    label: "A* · Manhattan",
    spec: { algorithm: "astar", heuristic: "manhattan" },
  },
  {
    id: "astar+euclidean",
    label: "A* · Euclidean",
    spec: { algorithm: "astar", heuristic: "euclidean" },
  },
  { id: "astar+zero", label: "A* · zero (= UCS)", spec: { algorithm: "astar", heuristic: "zero" } },
  {
    id: "astar+weighted",
    label: "A* · weighted ×2",
    spec: { algorithm: "astar", heuristic: "weighted" },
  },
];

export function SearchPanel() {
  const view = useView();
  const sessionId = useSim((s) => s.sessionId);
  const overlay = useUi((s) => s.overlay);
  const setOverlay = useUi((s) => s.setOverlay);
  const compare = useUi((s) => s.compare);
  const setCompare = useUi((s) => s.setCompare);
  const [picked, setPicked] = useState(["bfs", "ucs", "astar+manhattan"]);
  const [target, setTarget] = useState<string>("");
  const run = useMutation({
    mutationFn: (body: { runs: RunSpec[]; tick: number; target?: string }) =>
      api.compare({ session_id: sessionId ?? "", ...body }),
    onSuccess: (data) => {
      setCompare(data);
      setOverlay(null);
    },
  });

  if (!view || !sessionId) return <Empty>Start a scenario to compare search algorithms.</Empty>;
  const waiting = view.state.people.filter((p) => p.status === "WAITING");
  const chosen = target || view.target || waiting[0]?.id || "";
  const result = compare?.tick === view.tick ? compare : undefined;
  const maxExpanded = Math.max(1, ...(result?.runs.map((r) => r.expanded) ?? [1]));
  const searches = eventsOf(view, "RouteComputed");

  return (
    <div className="h-full overflow-y-auto">
      <Section title="Compare algorithms on one problem">
        <p className="mb-2 text-sm text-dim">
          Agent at ({view.state.agent.pos.join(", ")}) → a waiting person, tick {view.tick}. Every
          number below is measured by the engine.
        </p>
        <label className="mb-2 block text-xs text-dim">
          Target
          <select
            className="mt-1 w-full rounded-md border border-line bg-raised px-2 py-1.5 text-sm text-ink"
            value={chosen}
            onChange={(e) => setTarget(e.target.value)}
          >
            {waiting.map((p) => (
              <option key={p.id} value={p.id}>
                {p.id} at ({p.pos.join(", ")})
              </option>
            ))}
          </select>
        </label>
        <div className="mb-3 grid grid-cols-2 gap-x-3 gap-y-1">
          {CHOICES.map((c) => (
            <label key={c.id} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={picked.includes(c.id)}
                onChange={(e) =>
                  setPicked(e.target.checked ? [...picked, c.id] : picked.filter((p) => p !== c.id))
                }
              />
              {c.label}
            </label>
          ))}
        </div>
        <Btn
          tone="primary"
          disabled={run.isPending || picked.length === 0 || waiting.length === 0}
          onClick={() =>
            run.mutate({
              tick: view.tick,
              target: chosen,
              runs: CHOICES.filter((c) => picked.includes(c.id)).map((c) => c.spec),
            })
          }
        >
          {run.isPending ? "Searching…" : "Run comparison"}
        </Btn>
        {waiting.length === 0 && (
          <p className="mt-2 text-sm text-dim">Nobody is waiting at this tick.</p>
        )}
        {run.isError && <p className="mt-2 text-sm text-bad">{run.error.message}</p>}
      </Section>

      {result && (
        <Section title={`Results: ${result.target_id} at (${result.goal.join(", ")})`}>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-dim">
                <tr>
                  <th className="py-1 pr-2 font-medium">Algorithm</th>
                  <th className="px-1 text-right font-medium">Cost</th>
                  <th className="px-1 text-right font-medium">Expanded</th>
                  <th className="px-1 text-right font-medium">Gen.</th>
                  <th className="px-1 text-right font-medium">ms</th>
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
                    <td className="py-1.5 pr-2 font-medium">{r.label.replace("astar+", "A* ")}</td>
                    <td className="px-1 text-right tabular-nums">{fmt(r.cost)}</td>
                    <td className="px-1 text-right tabular-nums">{r.expanded}</td>
                    <td className="px-1 text-right tabular-nums">{r.generated}</td>
                    <td className="px-1 text-right tabular-nums">{r.time_ms.toFixed(2)}</td>
                    <td className="pl-2 whitespace-nowrap">
                      {!r.found ? (
                        <Chip tone="bad">no route</Chip>
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
                <span className="w-32 shrink-0 truncate">{r.label.replace("astar+", "A* ")}</span>
                <div className="h-3 flex-1 rounded bg-bg">
                  <div
                    className="h-3 rounded bg-accent"
                    style={{ width: `${(r.expanded / maxExpanded) * 100}%` }}
                  />
                </div>
                <span className="w-8 text-right tabular-nums">{r.expanded}</span>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs text-dim">
            "vs UCS" compares each path cost with a reference uniform-cost run; it is computed, not
            assumed. Click a row to paint its explored cells and path on the grid (blue = expanded
            early, red = late).
          </p>
        </Section>
      )}

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
    </div>
  );
}

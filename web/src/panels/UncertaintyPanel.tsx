import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type Belief, type Network } from "../api/client";
import { Lines } from "../components/Chart";
import { Btn, Chip, Empty, Section } from "../components/ui";
import { useView } from "../store/sim";
import { useUi } from "../store/ui";

type Tri = boolean | null; // observed true / observed false / not observed
const pct = (p: number) => `${(p * 100).toFixed(1)}%`;

// Fixed layout for the sensor network: causes on top, sensors below.
const POS: Record<string, [number, number]> = {
  Fire: [185, 26],
  Smoke: [50, 96],
  Heat: [140, 96],
  Trapped: [250, 96],
  Voice: [250, 162],
};

function Diagram({
  net,
  evidence,
  query,
}: {
  net: Network;
  evidence: Record<string, Tri>;
  query: string;
}) {
  return (
    <svg viewBox="0 0 340 190" className="w-full" role="img" aria-label="Bayesian network">
      <title>Sensor network: Fire causes Smoke, Heat and Trapped; Trapped causes Voice</title>
      <defs>
        <marker
          id="arrow"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="7"
          markerHeight="7"
          orient="auto"
        >
          <path d="M0,0 L10,5 L0,10 z" fill="#5c636c" />
        </marker>
      </defs>
      {net.nodes.flatMap((n) =>
        n.parents.map((parent) => {
          const a = POS[parent];
          const b = POS[n.name];
          if (!a || !b) return null;
          return (
            <line
              key={`${parent}-${n.name}`}
              x1={a[0]}
              y1={a[1] + 14}
              x2={b[0]}
              y2={b[1] - 16}
              stroke="#5c636c"
              strokeWidth="1.5"
              markerEnd="url(#arrow)"
            />
          );
        }),
      )}
      {net.nodes.map((n) => {
        const at = POS[n.name];
        if (!at) return null;
        const e = evidence[n.name];
        const observed = e !== null && e !== undefined;
        return (
          <g key={n.name}>
            <rect
              x={at[0] - 40}
              y={at[1] - 15}
              width="80"
              height="30"
              rx="15"
              fill={observed ? "#eeebe2" : "#fbfaf7"}
              stroke={n.name === query ? "#b8322a" : observed ? "#1f4fa3" : "#d9d4c7"}
              strokeWidth={n.name === query ? 2.5 : 1.5}
              strokeDasharray={observed ? "" : "4 3"}
            />
            <text x={at[0]} y={at[1] + 4} textAnchor="middle" fill="#1c2229" fontSize="12">
              {n.name}
              {observed ? (e ? " = T" : " = F") : n.name === query ? " ?" : ""}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function BeliefRow({ b, onLoad }: { b: Belief; onLoad: () => void }) {
  return (
    <li className="rounded border border-line p-2">
      <div className="flex items-center justify-between">
        <span className="font-semibold">{b.person_id}</span>
        <span className="text-xs text-dim">
          prior P(Fire) {pct(b.prior_fire)} → Risk{" "}
          <span className="text-base text-ink">{b.risk}</span>/5
        </span>
      </div>
      <div className="my-1 flex flex-wrap gap-1">
        {Object.entries(b.evidence).map(([k, v]) => (
          <Chip key={k} tone={v ? "warn" : "default"}>
            {k} {v ? "✓" : "✗"}
          </Chip>
        ))}
      </div>
      <div className="flex items-center gap-2 text-xs">
        <span className="w-24 text-dim">P(Trapped | e)</span>
        <div className="h-3 flex-1 rounded bg-bg">
          <div className="h-3 rounded bg-warn" style={{ width: pct(b.p_trapped) }} />
        </div>
        <span className="w-12 text-right tabular-nums">{pct(b.p_trapped)}</span>
      </div>
      <button type="button" className="mt-1 text-xs text-accent hover:underline" onClick={onLoad}>
        open in the lab ↓
      </button>
    </li>
  );
}

export function UncertaintyPanel() {
  const view = useView();
  const focus = useUi((s) => s.focus);
  const setFocus = useUi((s) => s.setFocus);
  const [prior, setPrior] = useState(0.4);
  const [net, setNet] = useState<Network | null>(null);
  const [evidence, setEvidence] = useState<Record<string, Tri>>({
    Smoke: true,
    Heat: true,
    Voice: null,
  });
  const [query, setQuery] = useState("Trapped");
  const [samples, setSamples] = useState(5000);
  const [seed, setSeed] = useState(1);

  const base = useQuery({ queryKey: ["network", prior], queryFn: () => api.network(prior) });
  useEffect(() => {
    if (base.data) setNet(base.data);
  }, [base.data]);

  const infer = useMutation({
    mutationFn: () =>
      api.infer({
        network: net ?? undefined,
        query,
        samples,
        seed,
        evidence: Object.fromEntries(
          Object.entries(evidence).filter(([k, v]) => v !== null && k !== query),
        ) as Record<string, boolean>,
      }),
  });

  // biome-ignore lint/correctness/useExhaustiveDependencies: fire once per focus request
  useEffect(() => {
    if (focus === "infer" && net) {
      setFocus(null);
      infer.mutate();
    }
  }, [focus, net]);

  const load = (b: Belief) => {
    setPrior(b.prior_fire);
    setEvidence({ ...b.evidence });
    setQuery("Trapped");
  };

  const out = infer.data;
  return (
    <div className="h-full overflow-y-auto">
      <Section title="What the agent believes this tick">
        {!view ? (
          <Empty>Start a scenario to see sensor readings.</Empty>
        ) : view.beliefs.length === 0 ? (
          <p className="text-sm text-dim">Nobody is waiting, so there is nothing to assess.</p>
        ) : (
          <ul className="space-y-2">
            {view.beliefs.map((b) => (
              <BeliefRow key={b.person_id} b={b} onLoad={() => load(b)} />
            ))}
          </ul>
        )}
        <p className="mt-2 text-xs text-dim">
          Risk(P) = round(5 × P(Trapped | sensors)), by exact inference. This is the Risk used in
          the priority score. Simulated sensors and illustrative probabilities, not real fire
          detection.
        </p>
      </Section>

      <Section title="Bayesian network lab">
        {net && <Diagram net={net} evidence={evidence} query={query} />}
        <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-dim">
          <label>
            Query
            <select
              className="mt-1 w-full rounded-md border border-line bg-raised px-2 py-1.5 text-sm text-ink"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            >
              {net?.nodes.map((n) => (
                <option key={n.name}>{n.name}</option>
              ))}
            </select>
          </label>
          <label>
            Prior P(Fire)
            <input
              type="number"
              min={0}
              max={1}
              step={0.05}
              className="mt-1 w-full rounded-md border border-line bg-raised px-2 py-1.5 text-sm text-ink"
              value={prior}
              onChange={(e) => setPrior(Math.min(1, Math.max(0, Number(e.target.value) || 0)))}
            />
          </label>
        </div>
        <fieldset className="mt-2">
          <legend className="text-xs text-dim">
            Evidence (click to cycle: unknown → true → false)
          </legend>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {net?.nodes
              .filter((n) => n.name !== query)
              .map((n) => {
                const v = evidence[n.name] ?? null;
                return (
                  <button
                    key={n.name}
                    type="button"
                    className={`rounded-full border px-2 py-0.5 text-xs ${
                      v === null
                        ? "border-line text-dim"
                        : v
                          ? "border-warn text-warn"
                          : "border-accent text-accent"
                    }`}
                    onClick={() =>
                      setEvidence({ ...evidence, [n.name]: v === null ? true : v ? false : null })
                    }
                  >
                    {n.name}: {v === null ? "unknown" : v ? "true" : "false"}
                  </button>
                );
              })}
          </div>
        </fieldset>

        <details className="mt-3">
          <summary className="cursor-pointer text-xs text-accent">
            Edit conditional probability tables
          </summary>
          <div className="mt-2 space-y-2">
            {net?.nodes.map((n, ni) => (
              <div key={n.name} className="text-xs">
                <div className="text-dim">
                  P({n.name} = true{n.parents.length ? ` | ${n.parents.join(", ")}` : ""})
                </div>
                <div className="flex flex-wrap gap-2">
                  {n.cpt.map((row, ri) => (
                    <label key={row.given.join()} className="flex items-center gap-1">
                      <span className="text-dim">
                        {row.given.length
                          ? row.given.map((g) => (g ? "T" : "F")).join(",")
                          : "prior"}
                      </span>
                      <input
                        type="number"
                        min={0}
                        max={1}
                        step={0.05}
                        aria-label={`P(${n.name} | ${row.given.join(",") || "no parents"})`}
                        className="w-16 rounded border border-line bg-raised px-1 py-0.5 text-ink"
                        value={row.p_true}
                        onChange={(e) => {
                          const p = Math.min(1, Math.max(0, Number(e.target.value) || 0));
                          setNet({
                            nodes: net.nodes.map((m, mi) =>
                              mi !== ni
                                ? m
                                : {
                                    ...m,
                                    cpt: m.cpt.map((r, i) => (i === ri ? { ...r, p_true: p } : r)),
                                  },
                            ),
                          });
                        }}
                      />
                    </label>
                  ))}
                </div>
              </div>
            ))}
            <Btn onClick={() => base.data && setNet(base.data)}>Reset tables</Btn>
          </div>
        </details>

        <div className="mt-3 flex items-end gap-2 text-xs text-dim">
          <label className="flex-1">
            Samples
            <input
              type="number"
              min={1}
              max={200000}
              className="mt-1 w-full rounded-md border border-line bg-raised px-2 py-1.5 text-sm text-ink"
              value={samples}
              onChange={(e) =>
                setSamples(Math.min(200000, Math.max(1, Number(e.target.value) || 1)))
              }
            />
          </label>
          <label className="w-20">
            Seed
            <input
              type="number"
              className="mt-1 w-full rounded-md border border-line bg-raised px-2 py-1.5 text-sm text-ink"
              value={seed}
              onChange={(e) => setSeed(Math.round(Number(e.target.value) || 0))}
            />
          </label>
          <Btn tone="primary" disabled={infer.isPending || !net} onClick={() => infer.mutate()}>
            {infer.isPending ? "Inferring…" : "Infer"}
          </Btn>
        </div>
        {infer.isError && <p className="mt-2 text-sm text-bad">{infer.error.message}</p>}
      </Section>

      {out && (
        <Section title={`P(${out.query} | evidence)`}>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className="text-2xl font-semibold tabular-nums">{pct(out.p_true)}</span>
            <Chip tone="accent">exact</Chip>
            {out.query === "Trapped" && <Chip>Risk {out.risk}/5</Chip>}
          </div>
          <table className="w-full text-left text-xs">
            <thead className="text-dim">
              <tr>
                <th className="py-1 font-medium">Method</th>
                <th className="px-1 text-right font-medium">P(true)</th>
                <th className="px-1 text-right font-medium">Error</th>
                <th className="px-1 text-right font-medium">Work</th>
              </tr>
            </thead>
            <tbody>
              {out.exact.map((e) => (
                <tr key={e.method} className="border-t border-line">
                  <td className="py-1.5">{e.method} (exact)</td>
                  <td className="px-1 text-right tabular-nums">{e.p_true.toFixed(4)}</td>
                  <td className="px-1 text-right tabular-nums">0</td>
                  <td className="px-1 text-right tabular-nums">{e.work} rows</td>
                </tr>
              ))}
              {out.sampled.map((s) => (
                <tr key={s.method} className="border-t border-line">
                  <td className="py-1.5">{s.method.replace("_", " ")}</td>
                  <td className="px-1 text-right tabular-nums">{s.p_true?.toFixed(4) ?? "–"}</td>
                  <td className="px-1 text-right tabular-nums">{s.error?.toFixed(4) ?? "–"}</td>
                  <td className="px-1 text-right tabular-nums">
                    {Math.round(s.used)}/{s.samples} used
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-3">
            <Lines
              series={out.sampled.map((s) => ({
                name: s.method.replace("_", " "),
                points: s.curve.map((c) => ({ x: c.n, y: c.error })),
              }))}
              xLabel="samples (log scale)"
              yLabel="|estimate − exact|"
              reference={0}
              logX
            />
          </div>
          <p className="mt-1 text-xs text-dim">
            Enumeration and variable elimination must agree. Sampling error shrinks as samples grow;
            rejection sampling wastes the samples that contradict the evidence.
          </p>
        </Section>
      )}
    </div>
  );
}

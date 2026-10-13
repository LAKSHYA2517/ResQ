import { api } from "../api/client";
import { useBuilder } from "../store/builder";
import { useSim, useView } from "../store/sim";
import { useUi } from "../store/ui";
import { Btn, Chip, fmt, Section } from "./ui";

function Row({ k, v }: { k: string; v: string | number }) {
  return (
    <div className="flex justify-between gap-2 py-0.5">
      <dt className="text-dim">{k}</dt>
      <dd className="tabular-nums">{v}</dd>
    </div>
  );
}

export function RunSidebar() {
  const view = useView();
  const scenarioId = useSim((s) => s.scenarioId);
  const setMode = useUi((s) => s.setMode);
  const load = useBuilder((s) => s.load);
  if (!view) return null;
  const m = view.metrics;

  const edit = async () => {
    if (scenarioId) load((await api.scenario(scenarioId)).scenario);
    setMode("build");
  };

  return (
    <div className="h-full overflow-y-auto">
      <Section title="Mission" right={<Btn onClick={() => void edit()}>Edit scenario</Btn>}>
        <div className="mb-2 flex flex-wrap gap-1.5">
          <Chip
            tone={view.status === "complete" ? "go" : view.status === "stuck" ? "warn" : "accent"}
          >
            {view.status}
          </Chip>
          <Chip>target {view.target ?? "none"}</Chip>
        </div>
        <h4 className="mt-3 text-xs text-dim">People</h4>
        <ul className="mt-1 space-y-1 text-sm">
          {view.state.people.map((p) => (
            <li key={p.id} className="flex items-center justify-between">
              <span>
                <span className="font-semibold">{p.id}</span>{" "}
                <span className="text-dim">
                  risk {p.risk} · urg {p.urgency}
                </span>
              </span>
              <Chip
                tone={p.status === "EVACUATED" ? "go" : p.status === "TRAPPED" ? "bad" : "accent"}
              >
                {p.status.toLowerCase()}
              </Chip>
            </li>
          ))}
        </ul>
        <h4 className="mt-3 text-xs text-dim">Exits</h4>
        <ul className="mt-1 space-y-1 text-sm">
          {view.state.exits.map((e) => (
            <li key={e.id} className="flex items-center justify-between">
              <span className="font-semibold">{e.id}</span>
              <Chip tone={e.available && e.usable ? "go" : "bad"}>
                {!e.available ? "blocked" : e.usable ? "open" : "unusable"}
              </Chip>
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Measured by the engine">
        <dl className="text-sm">
          <Row k="Moves" v={m.moves} />
          <Row k="Cost paid" v={fmt(m.path_cost)} />
          <Row k="Plans / replans" v={`${m.plans} / ${m.replans}`} />
          <Row k="A* runs" v={m.searches} />
          <Row k="Cells expanded (A*)" v={m.nodes_expanded} />
          <Row k="States expanded (planner)" v={m.plan_nodes_expanded} />
          <Row k="KB facts (base / derived)" v={`${m.kb_base} / ${m.kb_derived}`} />
          <Row k="Forward-chaining passes" v={m.kb_iterations} />
          <Row k="Time this tick" v={`${fmt(m.timings_ms.total ?? 0, 2)} ms`} />
        </dl>
      </Section>

      <Section title="This tick">
        <dl className="text-sm">
          {Object.entries(m.timings_ms)
            .filter(([k]) => k !== "total")
            .map(([k, v]) => (
              <Row key={k} k={k} v={`${fmt(v, 2)} ms`} />
            ))}
        </dl>
      </Section>
    </div>
  );
}

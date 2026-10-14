import { Pencil } from "lucide-react";
import { api } from "../api/client";
import { useBuilder } from "../store/builder";
import { useSim, useView } from "../store/sim";
import { useUi } from "../store/ui";
import { EventLog } from "./Controls";
import { Btn, fmt, Section, Status } from "./ui";

const PERSON_TONE = { EVACUATED: "go", TRAPPED: "bad", CARRIED: "accent", WAITING: "dim" } as const;

/** Run mode, left column: who is where, which exits work, and what happened. */
export function RunSidebar() {
  const view = useView();
  const scenarioId = useSim((s) => s.scenarioId);
  const setMode = useUi((s) => s.setMode);
  const load = useBuilder((s) => s.load);
  if (!view) return null;

  const edit = async () => {
    if (scenarioId) load((await api.scenario(scenarioId)).scenario);
    setMode("build");
  };

  return (
    <div className="flex h-full flex-col">
      <Section
        title="People"
        right={
          <Btn tone="ghost" onClick={() => void edit()}>
            <Pencil size={14} /> Edit scenario
          </Btn>
        }
      >
        <ul className="space-y-1">
          {view.state.people.map((p) => (
            <li key={p.id} className="flex items-center justify-between gap-2">
              <span>
                <span className="font-semibold">{p.id}</span>{" "}
                <span className="text-xs text-dim">
                  risk {p.risk} · urgency {p.urgency}
                </span>
              </span>
              <Status tone={PERSON_TONE[p.status]}>{p.status.toLowerCase()}</Status>
            </li>
          ))}
        </ul>
      </Section>
      <Section title="Exits">
        <ul className="space-y-1">
          {view.state.exits.map((e) => (
            <li key={e.id} className="flex items-center justify-between">
              <span className="font-semibold">{e.id}</span>
              <Status tone={e.available && e.usable ? "go" : "bad"}>
                {!e.available ? "blocked" : e.usable ? "open" : "unusable"}
              </Status>
            </li>
          ))}
        </ul>
      </Section>
      <Section title="Run">
        <dl className="text-sm">
          <Row k="Moves" v={view.metrics.moves} />
          <Row k="Cost paid" v={fmt(view.metrics.path_cost)} />
          <Row k="Plans / replans" v={`${view.metrics.plans} / ${view.metrics.replans}`} />
          <Row k="A* runs" v={view.metrics.searches} />
        </dl>
      </Section>
      <div className="min-h-0 flex-1">
        <EventLog />
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string | number }) {
  return (
    <div className="flex justify-between gap-2 py-0.5">
      <dt className="text-dim">{k}</dt>
      <dd className="font-mono text-[13px]">{v}</dd>
    </div>
  );
}

/** The rest of the engine counters for the viewed tick (the headline four are in the sidebar). */
export function Metrics() {
  const view = useView();
  if (!view) return null;
  const m = view.metrics;
  return (
    <Section title="Measured by the engine">
      <dl className="text-sm">
        <Row k="Cells expanded (A*)" v={m.nodes_expanded} />
        <Row k="States expanded (planner)" v={m.plan_nodes_expanded} />
        <Row k="KB facts (base / derived)" v={`${m.kb_base} / ${m.kb_derived}`} />
        <Row k="Forward-chaining passes" v={m.kb_iterations} />
        {Object.entries(m.timings_ms).map(([k, v]) => (
          <Row key={k} k={k === "total" ? "Time this tick" : `  ${k}`} v={`${fmt(v, 2)} ms`} />
        ))}
      </dl>
    </Section>
  );
}

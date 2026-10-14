import { Btn, Chip, Section } from "../components/ui";
import { useSim } from "../store/sim";
import { type Tab, useUi } from "../store/ui";

interface Row {
  module: string;
  topics: string;
  feature: string;
  tab?: Tab;
  focus?: string;
  status: "built" | "Phase 5" | "out of scope";
}

/** Course map (BCSE306L). "Run it" opens the feature; nothing here is a result. */
const ROWS: Row[] = [
  {
    module: "1 · Introduction",
    topics: "Intelligent agents, structure of agents, environments",
    feature: "PEAS table and environment properties that follow the scenario's mode",
    tab: "agent",
    status: "built",
  },
  {
    module: "1 · Introduction",
    topics: "Agent types",
    feature: "Benchmark: simple-reflex vs goal-based vs utility-based agents",
    status: "Phase 5",
  },
  {
    module: "2 · Search",
    topics: "State space, BFS, UCS, DFS, DLS, IDDFS, greedy, A*",
    feature: "Eight algorithms on one problem, the Algorithm Race, and the heuristic lab",
    tab: "search",
    focus: "race",
    status: "built",
  },
  {
    module: "3 · Local search",
    topics: "Hill climbing, simulated annealing, genetic algorithm",
    feature: "Rescue-order optimizer against greedy and the exhaustive optimum",
    tab: "optimize",
    focus: "order",
    status: "built",
  },
  {
    module: "3 · Adversarial search",
    topics: "Game trees, minimax, alpha-beta pruning",
    feature: "Fire (MAX) against the agent (MIN): same move, fewer nodes with pruning",
    tab: "optimize",
    focus: "adversarial",
    status: "built",
  },
  {
    module: "4 · Logic",
    topics: "Propositional and first-order logic, unification, forward chaining",
    feature: "Horn-clause KB with provenance for every derived fact",
    tab: "reasoning",
    status: "built",
  },
  {
    module: "4 · Logic",
    topics: "Backward chaining, resolution",
    feature: '"Prove it": proof tree and resolution refutation for any goal',
    tab: "reasoning",
    focus: "prove:AtRisk(P)",
    status: "built",
  },
  {
    module: "5 · Uncertainty",
    topics: "Bayes rule, Bayesian networks, exact and approximate inference",
    feature: "Sensor network setting each person's Risk; enumeration, elimination, three samplers",
    tab: "uncertainty",
    focus: "infer",
    status: "built",
  },
  {
    module: "6 · Planning",
    topics: "Classical planning, forward and backward state-space search",
    feature: "STRIPS domain; progression and regression planners with equal cost",
    tab: "planning",
    focus: "planners",
    status: "built",
  },
  {
    module: "6 · Planning",
    topics: "Nondeterministic domains, execution monitoring, replanning",
    feature: "Plan monitor: inject an event and watch the precondition fail and the replan",
    tab: "planning",
    status: "built",
  },
  {
    module: "6 · Planning",
    topics: "Planning graphs, hierarchical planning",
    feature: "Planning-graph viewer and HTN decomposition tree",
    status: "Phase 5",
  },
  {
    module: "7 · Communicating, perceiving",
    topics: "NLP, perception",
    feature: "Not built. Sensors are simulated inputs to the Bayesian network.",
    status: "out of scope",
  },
  {
    module: "8 · Contemporary issues",
    topics: "Ethics",
    feature: "Triage ethics and limits of classical AI (docs/ETHICS.md)",
    status: "Phase 5",
  },
];

export function SyllabusPanel() {
  const setTab = useUi((s) => s.setTab);
  const setFocus = useUi((s) => s.setFocus);
  const hasSession = useSim((s) => s.sessionId !== null);
  return (
    <div className="h-full overflow-y-auto">
      <Section title="Syllabus coverage (BCSE306L)">
        {!hasSession && (
          <p className="mb-2 text-sm text-warn">Start a scenario first, then use Run it.</p>
        )}
        <ul className="space-y-2">
          {ROWS.map((r) => (
            <li key={r.module + r.feature} className="rounded border border-line p-2">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="text-xs font-semibold text-accent">{r.module}</div>
                  <div className="text-xs text-dim">{r.topics}</div>
                </div>
                {r.status === "built" ? (
                  <Btn
                    disabled={!hasSession || !r.tab}
                    onClick={() => {
                      if (!r.tab) return;
                      setFocus(r.focus ?? null);
                      setTab(r.tab);
                    }}
                  >
                    Run it
                  </Btn>
                ) : (
                  <Chip tone={r.status === "out of scope" ? "default" : "warn"}>{r.status}</Chip>
                )}
              </div>
              <div className="mt-1 text-sm">{r.feature}</div>
            </li>
          ))}
        </ul>
      </Section>
    </div>
  );
}

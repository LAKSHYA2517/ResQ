/** The guided demo. Every step performs real calls against the engine API; the captions only
 * describe what the engine returned. Steps that need later phases are listed, not faked. */

import { api } from "./api/client";
import { cellsIn } from "./lib/cells";
import { useBuilder } from "./store/builder";
import { useSim } from "./store/sim";
import { type Tab, useUi } from "./store/ui";

export interface DemoStep {
  title: string;
  caption: string;
  panel?: Tab;
  /** Phase that delivers this step, when it cannot run yet. */
  later?: string;
  run?: () => Promise<void>;
}

const sim = () => useSim.getState();
const ui = () => useUi.getState();

async function until(done: () => boolean, ms = 60000) {
  const t0 = Date.now();
  while (!done() && Date.now() - t0 < ms) await new Promise((r) => setTimeout(r, 50));
}

async function loadShowcase() {
  await sim().start("showcase");
  const scenario = (await api.scenario("showcase")).scenario;
  useBuilder.getState().load(scenario);
  ui().setMode("run");
  ui().setOverlay(null);
  sim().setHighlight([]);
}

export const STEPS: DemoStep[] = [
  {
    title: "Load Showcase",
    caption:
      "One agent, three people, rubble, walls, a spreading fire and two exits. The scenario was loaded and started by the engine API.",
    panel: "reasoning",
    run: loadShowcase,
  },
  {
    title: "The state is structured data",
    caption:
      "The world is plain data: grid, terrain, fire, hot zone, agent, people, exits. The grid is only a picture of this.",
    panel: "reasoning",
    run: async () => ui().setShowState(true),
  },
  {
    title: "Facts and rules",
    caption:
      "The state is translated into base facts, and ten Horn rules describe what follows from them. Closed-world assumption: what is not known is false.",
    panel: "reasoning",
    run: async () => ui().setShowState(false),
  },
  {
    title: "Forward chaining",
    caption:
      "Rules fire to a fixpoint. Unsafe, Hot and AtRisk appear with provenance: click a derived fact to see the rule, the bindings and the premises. The highlighted cells are where the facts apply.",
    panel: "reasoning",
    run: async () => {
      const head = sim().head;
      const atRisk = head?.derived.filter((d) => d.fact.startsWith("AtRisk")) ?? [];
      sim().setHighlight(atRisk.flatMap((d) => cellsIn(d.premises.join(" "))));
    },
  },
  {
    title: "Prove it",
    caption:
      "The same question asked three independent ways: is AtRisk(P) in the forward-chained fixpoint, can backward chaining build a proof tree from base facts, and (for a ground goal) does resolution reach the empty clause? They must agree.",
    panel: "reasoning",
    run: async () => {
      const target = sim().head?.target ?? "p2";
      ui().setFocus(`prove:AtRisk(${target})`);
    },
  },
  {
    title: "Bayesian sensor network",
    caption:
      "Each person's zone has smoke, heat and voice sensors. Exact inference gives P(Trapped | readings), and Risk = round(5 × that). The lab runs enumeration, variable elimination and three samplers, and plots the sampling error shrinking towards the exact answer.",
    panel: "uncertainty",
    run: async () => {
      sim().setHighlight([]);
      ui().setFocus("infer");
    },
  },
  {
    title: "Priority scores",
    caption:
      "Priority = 5·Risk + 3·Urgency − 1·PathCost, where PathCost is a real A* cost. The far, critical person outranks the near, safe one.",
    panel: "planning",
    run: async () => {
      sim().setHighlight([]);
      const target = sim().head?.target;
      const person = sim().head?.state.people.find((p) => p.id === target);
      if (person) sim().setHighlight([person.pos]);
    },
  },
  {
    title: "Algorithm race",
    caption:
      "BFS, DFS, UCS, Greedy and A* on the same target, replaying their real expansion order at the same pace. UCS and A* agree on cost; A* expands far fewer cells; DFS is not optimal, and Greedy only sometimes is. Every counter is measured. Close the race to continue.",
    panel: "search",
    run: async () => ui().setFocus("race"),
  },
  {
    title: "Rescue-order optimizer",
    caption:
      "In which order should everyone be rescued? Hill climbing, simulated annealing and a genetic algorithm against greedy-by-priority, with the exhaustive optimum as the reference line. (Load Mass Evacuation for seven people and 5040 orders.)",
    panel: "optimize",
    run: async () => ui().setFocus("order"),
  },
  {
    title: "Plan",
    caption:
      "A STRIPS plan: Travel, PickUp, Travel, DropOff, each Travel costed by A*. Forward search (from the state) and regression (from the goal) are run on the same problem and must find the same cost. The HTN tree arrives in Phase 5.",
    panel: "planning",
    run: async () => {
      ui().setOverlay(null);
      sim().setHighlight([]);
      ui().setFocus("planners");
    },
  },
  {
    title: "Execute",
    caption:
      "The agent executes one validated action per tick while the fire spreads (seeded, so it is reproducible). Watch the route and the hot zone change.",
    panel: "planning",
    run: async () => {
      await until(() => sim().head !== null && !sim().busy);
      sim().setRunning(true);
      await until(() => (sim().head?.tick ?? 0) >= 5 || (sim().head?.finished ?? true));
      sim().setRunning(false);
      await until(() => !sim().running);
    },
  },
  {
    title: "Fire on the route",
    caption:
      "A new fire is injected two cells ahead on the current route. The agent re-checks its plan against the new facts, finds the broken precondition and replans.",
    panel: "reasoning",
    run: async () => {
      const head = sim().head;
      const cell = head?.route[2];
      if (cell) await sim().inject("NEW_FIRE", { pos: cell });
    },
  },
  {
    title: "Fact diff and the replan",
    caption:
      "The knowledge base diff is on the Logic tab; the Plan tab shows the invalidated plan, the reason and the new plan.",
    panel: "planning",
  },
  {
    title: "Adversarial fire",
    caption:
      "Now treat the fire as an opponent. Minimax and alpha-beta search the same game tree from the agent's position: same best step and value, far fewer nodes with pruning.",
    panel: "optimize",
    run: async () => ui().setFocus("adversarial"),
  },
  {
    title: "Final outcome",
    caption:
      "The run finishes and the measured totals appear in the sidebar. Replaying the scenario, seed and event log reproduces every tick (scrub the timeline). The agent-type benchmark arrives in Phase 5.",
    panel: "planning",
    run: async () => {
      sim().setRunning(true);
      await until(() => sim().head?.finished ?? true, 120000);
      sim().setRunning(false);
    },
  },
  {
    title: "Impossible scenario",
    caption:
      "When no valid plan exists the agent says so and why, built from the failed search and the derived facts. It never invents a route.",
    panel: "planning",
    run: async () => {
      await sim().start("impossible");
      sim().setHighlight([]);
    },
  },
];

export async function goToStep(i: number, execute = true) {
  const step = STEPS[i];
  if (!step) return;
  ui().setDemoStep(i);
  if (step.panel) ui().setTab(step.panel);
  if (execute && step.run && !step.later) await step.run();
}

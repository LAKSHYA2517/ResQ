import * as Tabs from "@radix-ui/react-tabs";
import { useQuery } from "@tanstack/react-query";
import { Command, Download, Presentation } from "lucide-react";
import { type ReactNode, useEffect, useMemo, useState } from "react";
import { api, type Cell } from "./api/client";
import { Builder } from "./components/Builder";
import { CommandPalette } from "./components/CommandPalette";
import { Controls } from "./components/Controls";
import { DemoBar } from "./components/DemoBar";
import { ExplainDialog } from "./components/ExplainDialog";
import { GridCanvas } from "./components/GridCanvas";
import { RunSidebar } from "./components/RunSidebar";
import { Btn, Status } from "./components/ui";
import { goToStep } from "./demo";
import { cellName, key } from "./lib/cells";
import { draftToState } from "./lib/draft";
import type { Scene } from "./lib/draw";
import { saveReport } from "./lib/report";
import { AgentPanel } from "./panels/AgentPanel";
import { OptimizePanel } from "./panels/OptimizePanel";
import { PlanningPanel } from "./panels/PlanningPanel";
import { ReasoningPanel } from "./panels/ReasoningPanel";
import { SearchPanel } from "./panels/SearchPanel";
import { SyllabusPanel } from "./panels/SyllabusPanel";
import { UncertaintyPanel } from "./panels/UncertaintyPanel";
import { useBuilder } from "./store/builder";
import { useSim, useView } from "./store/sim";
import { type Tab, useUi } from "./store/ui";

const LEAVES: Record<Tab, [string, () => ReactNode]> = {
  reasoning: ["Logic", () => <ReasoningPanel />],
  uncertainty: ["Bayes", () => <UncertaintyPanel />],
  search: ["Search", () => <SearchPanel />],
  planning: ["Plan", () => <PlanningPanel />],
  optimize: ["Optimize", () => <OptimizePanel />],
  agent: ["Agent", () => <AgentPanel />],
  syllabus: ["Syllabus", () => <SyllabusPanel />],
};

// Four top-level tabs; a group with several leaves shows them as sub-tabs.
const GROUPS: [string, Tab[]][] = [
  ["Reasoning", ["reasoning", "uncertainty"]],
  ["Search", ["search"]],
  ["Plan", ["planning"]],
  ["Analysis", ["optimize", "agent", "syllabus"]],
];

const reducedMotion =
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

export function App() {
  const mode = useUi((s) => s.mode);
  const setMode = useUi((s) => s.setMode);
  const tab = useUi((s) => s.tab);
  const setTab = useUi((s) => s.setTab);
  const demoStep = useUi((s) => s.demoStep);
  const sim = useSim();
  const view = useView();
  const builder = useBuilder();
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 5000 });
  const [hover, setHover] = useState<Cell | null>(null);

  // Start the builder on the Showcase scenario so the first screen is never empty.
  const { load } = builder;
  useEffect(() => {
    api
      .scenario("showcase")
      .then((s) => load(s.scenario))
      .catch(() => undefined);
  }, [load]);

  // Keyboard: Ctrl/Cmd+K = command palette, space = play/pause, → = step, ← = scrub back.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        useUi.getState().setPalette(!useUi.getState().palette);
        return;
      }
      const tag = (e.target as HTMLElement | null)?.tagName ?? "";
      if (["INPUT", "SELECT", "TEXTAREA", "BUTTON"].includes(tag)) return;
      const s = useSim.getState();
      if (!s.head || useUi.getState().mode !== "run") return;
      if (e.code === "Space") {
        e.preventDefault();
        if (!s.head.finished) s.setRunning(!s.running);
      } else if (e.key === "ArrowRight") {
        void s.step();
      } else if (e.key === "ArrowLeft") {
        void s.scrub(Math.max(0, (s.viewTick ?? s.head.tick) - 1));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const running = mode === "run" && view !== null;
  const overlay = useUi((s) => s.overlay);
  const cache = useSim((s) => s.cache);

  const scene: Scene | null = useMemo(() => {
    if (!running || !view) {
      return {
        state: draftToState(builder.draft),
        route: [],
        waypoints: [],
        trail: [],
        explored: [],
        exploredShown: 0,
        targetId: null,
        issues: builder.issues.flatMap((i) => (i.cell ? [i.cell as Cell] : [])),
        highlight: [],
        hover,
        pickMode: false,
        motion: !reducedMotion,
      };
    }
    const trail: Cell[] = [];
    for (let t = 0; t < view.tick; t++) {
      const snap = cache[t];
      if (snap) trail.push(snap.state.agent.pos);
    }
    const waypoints = view.plan
      .map((s, i) => ({ s, i }))
      .filter(({ s }) => s.name === "Travel" && s.route.length > 0)
      .map(({ s, i }) => ({ cell: s.route[s.route.length - 1] as Cell, label: String(i + 1) }));
    return {
      state: view.state,
      route: overlay ? overlay.path : view.route,
      waypoints: overlay ? [] : waypoints,
      trail,
      explored: overlay?.explored ?? [],
      exploredShown: 0,
      targetId: view.target,
      issues: [],
      highlight: sim.highlight,
      hover,
      pickMode: sim.pick !== null,
      motion: !reducedMotion,
    };
  }, [
    running,
    view,
    builder.draft,
    builder.issues,
    overlay,
    cache,
    sim.highlight,
    sim.pick,
    hover,
  ]);

  const label = running
    ? `Grid at tick ${view?.tick}: ${view?.state.people.length} people, ${view?.state.fire.length} fire cells`
    : `Scenario builder grid ${builder.draft.grid_size.join(" by ")}`;

  const onCell = (cell: Cell, phase: "down" | "move" | "up") => {
    if (running) {
      if (phase === "down" && sim.pick) void sim.inject(sim.pick, { pos: cell });
      else if (phase === "down") {
        const here = view?.state.people.find((p) => key(p.pos) === key(cell));
        if (here) sim.setHighlight([cell]);
      }
      return;
    }
    if (phase === "down") builder.beginStroke();
    if (phase === "up") return;
    const continuous = ["floor", "rubble", "wall", "fire", "erase"].includes(builder.tool);
    if (phase === "move" && !continuous) return;
    builder.paintAt(cell);
  };

  const apiDown = health.isError;

  return (
    <div className="flex h-full flex-col">
      <header className="flex h-12 items-center gap-4 border-b border-line bg-panel px-4">
        <h1 className="text-[15px] font-semibold tracking-tight">ResQ</h1>
        {running && view ? (
          <div className="flex items-center gap-4 border-l border-line pl-4 text-sm">
            <Status
              tone={view.status === "complete" ? "go" : view.status === "stuck" ? "warn" : "accent"}
            >
              tick {view.tick} · {view.status}
            </Status>
            <span>
              rescued {view.metrics.rescued}/{view.state.people.length}
            </span>
            <span className="text-dim">target {view.target ?? "none"}</span>
          </div>
        ) : (
          <span className="border-l border-line pl-4 text-sm text-dim">
            {builder.draft.name || "Untitled scenario"}
          </span>
        )}
        <div className="ml-auto flex items-center gap-2">
          <span className="mr-2 text-xs text-dim">
            {apiDown ? (
              <Status tone="bad">engine API unreachable</Status>
            ) : (
              <Status tone="go">engine v{health.data?.version ?? "…"}</Status>
            )}
          </span>
          <div className="flex overflow-hidden rounded-md border border-line" role="tablist">
            {(["build", "run"] as const).map((m) => (
              <button
                key={m}
                type="button"
                role="tab"
                aria-selected={mode === m}
                disabled={m === "run" && !sim.head}
                onClick={() => setMode(m)}
                className={`px-3 py-1 text-sm disabled:opacity-40 ${
                  mode === m ? "bg-accent text-white font-medium" : "bg-panel"
                }`}
              >
                {m === "build" ? "Build" : "Run"}
              </button>
            ))}
          </div>
          {sim.sessionId && (
            <Btn
              tone="ghost"
              title="Download the engine's report for this run (JSON and a printable page)"
              onClick={async () => {
                try {
                  saveReport(await api.report(sim.sessionId ?? ""));
                } catch (e) {
                  useSim.setState({ error: (e as Error).message });
                }
              }}
            >
              <Download size={15} /> Report
            </Btn>
          )}
          <Btn
            tone="ghost"
            title="Command palette (Ctrl/Cmd+K)"
            aria-label="Command palette"
            onClick={() => useUi.getState().setPalette(true)}
          >
            <Command size={15} />
          </Btn>
          <Btn
            tone={demoStep === null ? "default" : "primary"}
            disabled={apiDown || sim.busy}
            onClick={() => void goToStep(0, true)}
          >
            <Presentation size={15} /> Guided demo
          </Btn>
        </div>
      </header>

      <DemoBar />

      {sim.error && (
        <div role="alert" className="flex items-center gap-3 bg-bad/15 px-4 py-2 text-sm text-bad">
          <span className="flex-1">{sim.error}</span>
          <Btn tone="ghost" onClick={sim.clearError}>
            Dismiss
          </Btn>
        </div>
      )}

      <div className="grid min-h-0 flex-1 grid-cols-[272px_minmax(0,1fr)_440px]">
        <aside className="min-h-0 border-r border-line bg-panel" aria-label="Scenario">
          {running ? <RunSidebar /> : <Builder />}
        </aside>

        <main className="relative flex min-h-0 min-w-0 flex-col bg-bg">
          <div className="relative min-h-0 flex-1 p-3">
            {scene && (
              <GridCanvas
                scene={scene}
                label={label}
                onCell={onCell}
                onHover={setHover}
                cursor={
                  running
                    ? sim.pick
                      ? "crosshair"
                      : "default"
                    : builder.tool === "select"
                      ? "pointer"
                      : "crosshair"
                }
              />
            )}
            {running && overlay && (
              <div className="absolute top-4 left-4 rounded-md border border-accent bg-panel px-2 py-1 text-xs shadow-sm">
                Showing {overlay.label}: explored cells and path.{" "}
                <button
                  type="button"
                  className="text-accent underline"
                  onClick={() => useUi.getState().setOverlay(null)}
                >
                  clear
                </button>
              </div>
            )}
            {running && hover && view && (
              <div className="absolute right-4 bottom-4 rounded-md border border-line bg-panel px-2 py-1 font-mono text-xs text-dim">
                ({hover[0]}, {hover[1]}) {cellName(hover)}
                {view.state.hot.some((h) => key(h) === key(hover)) ? " · hot" : ""}
              </div>
            )}
          </div>
          <Legend running={running} />
          {running && <Controls />}
        </main>

        <aside
          className="flex min-h-0 flex-col border-l border-line bg-panel"
          aria-label="Analysis"
        >
          <Tabs.Root
            value={GROUPS.find(([, leaves]) => leaves.includes(tab))?.[0]}
            onValueChange={(g) => setTab(GROUPS.find(([name]) => name === g)?.[1][0] ?? tab)}
            className="flex min-h-0 flex-1 flex-col"
          >
            <Tabs.List className="flex border-b border-line px-2" aria-label="Analysis panels">
              {GROUPS.map(([name]) => (
                <Tabs.Trigger
                  key={name}
                  value={name}
                  className="border-b-2 border-transparent px-3 py-3 text-sm text-dim hover:text-ink data-[state=active]:border-accent data-[state=active]:font-medium data-[state=active]:text-ink"
                >
                  {name}
                </Tabs.Trigger>
              ))}
            </Tabs.List>
            {GROUPS.map(([name, leaves]) => (
              <Tabs.Content key={name} value={name} className="flex min-h-0 flex-1 flex-col">
                {leaves.length === 1 ? (
                  <div className="min-h-0 flex-1">{LEAVES[leaves[0] as Tab][1]()}</div>
                ) : (
                  <Tabs.Root
                    value={tab}
                    onValueChange={(v) => setTab(v as Tab)}
                    className="flex min-h-0 flex-1 flex-col"
                  >
                    <Tabs.List className="flex gap-1 border-b border-line px-3 py-2">
                      {leaves.map((id) => (
                        <Tabs.Trigger
                          key={id}
                          value={id}
                          className="rounded-md px-2.5 py-1 text-[13px] text-dim hover:text-ink data-[state=active]:bg-raised data-[state=active]:text-ink"
                        >
                          {LEAVES[id][0]}
                        </Tabs.Trigger>
                      ))}
                    </Tabs.List>
                    {leaves.map((id) => (
                      <Tabs.Content key={id} value={id} className="min-h-0 flex-1">
                        {LEAVES[id][1]()}
                      </Tabs.Content>
                    ))}
                  </Tabs.Root>
                )}
              </Tabs.Content>
            ))}
          </Tabs.Root>
        </aside>
      </div>

      <ExplainDialog />
      <CommandPalette />
    </div>
  );
}

const SWATCH: [string, string][] = [
  ["wall", "bg-[#2f353d]"],
  ["rubble", "bg-[#efe9dc] border border-[#8a7a62] border-dotted"],
  ["fire", "bg-[#c8402c]"],
  ["hot zone (+4 cost)", "bg-[rgba(214,110,40,0.25)]"],
  ["exit", "bg-[#e5f0e8] border border-go"],
];

function Legend({ running }: { running: boolean }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 pb-2 text-xs text-dim">
      {SWATCH.map(([name, cls]) => (
        <span key={name} className="inline-flex items-center gap-1.5">
          <span className={`size-3 rounded-[2px] ${cls}`} aria-hidden />
          {name}
        </span>
      ))}
      <span className="inline-flex items-center gap-1.5">
        <span className="size-3 rounded-full border-2 border-accent bg-white" aria-hidden />
        person
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="size-3 rounded-[2px] bg-ink" aria-hidden />
        agent
      </span>
      {running && (
        <span className="inline-flex items-center gap-1.5">
          <span className="h-0.5 w-4 bg-accent" aria-hidden />
          route
        </span>
      )}
    </div>
  );
}

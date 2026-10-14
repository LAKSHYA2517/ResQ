import * as Tabs from "@radix-ui/react-tabs";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { api, type Cell } from "./api/client";
import { Builder } from "./components/Builder";
import { CommandPalette } from "./components/CommandPalette";
import { Controls, EventLog } from "./components/Controls";
import { DemoBar } from "./components/DemoBar";
import { ExplainDialog } from "./components/ExplainDialog";
import { GridCanvas } from "./components/GridCanvas";
import { RunSidebar } from "./components/RunSidebar";
import { Btn, Chip } from "./components/ui";
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

const TABS: [Tab, string][] = [
  ["reasoning", "Logic"],
  ["search", "Search"],
  ["planning", "Plan"],
  ["uncertainty", "Bayes"],
  ["optimize", "Optimize"],
  ["agent", "Agent"],
  ["syllabus", "Syllabus"],
];

const reducedMotion =
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

export function App() {
  const mode = useUi((s) => s.mode);
  const setMode = useUi((s) => s.setMode);
  const tab = useUi((s) => s.tab);
  const setTab = useUi((s) => s.setTab);
  const demoStep = useUi((s) => s.demoStep);
  const presentation = useUi((s) => s.presentation);
  const setPresentation = useUi((s) => s.setPresentation);
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

  // Presentation mode scales every rem-based size (Tailwind) by raising the root font size.
  useEffect(() => {
    document.documentElement.style.fontSize = presentation ? "18px" : "";
  }, [presentation]);

  // Keyboard: Ctrl/Cmd+K = command palette, space = play/pause, → = step, ← = scrub back,
  // p = presentation mode.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        useUi.getState().setPalette(!useUi.getState().palette);
        return;
      }
      const tag = (e.target as HTMLElement | null)?.tagName ?? "";
      if (["INPUT", "SELECT", "TEXTAREA"].includes(tag)) return; // typing, not a shortcut
      if (e.key === "p" && !e.metaKey && !e.ctrlKey) {
        useUi.getState().setPresentation(!useUi.getState().presentation);
        return;
      }
      if (tag === "BUTTON") return; // space and arrows belong to the focused button
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
      <header className="flex items-center gap-3 border-b border-line bg-panel px-4 py-2">
        <h1 className="text-lg font-bold tracking-tight">
          ResQ<span className="text-accent">-AI</span>
        </h1>
        <span className={`hidden text-xs text-dim ${presentation ? "" : "xl:inline"}`}>
          classical-AI rescue agent · every number comes from the engine
        </span>
        <div className="ml-auto flex items-center gap-2">
          {apiDown ? (
            <Chip tone="bad">engine API unreachable</Chip>
          ) : (
            <Chip tone="go">engine v{health.data?.version ?? "…"}</Chip>
          )}
          <div className="flex overflow-hidden rounded-md border border-line" role="tablist">
            {(["build", "run"] as const).map((m) => (
              <button
                key={m}
                type="button"
                role="tab"
                aria-selected={mode === m}
                disabled={m === "run" && !sim.head}
                onClick={() => setMode(m)}
                className={`px-3 py-1.5 text-sm disabled:opacity-40 ${
                  mode === m ? "bg-accent text-bg font-semibold" : "bg-raised"
                }`}
              >
                {m === "build" ? "Build" : "Run"}
              </button>
            ))}
          </div>
          {sim.sessionId && (
            <Btn
              title="Download the engine's report for this run (JSON and a printable page)"
              onClick={async () => {
                try {
                  saveReport(await api.report(sim.sessionId ?? ""));
                } catch (e) {
                  useSim.setState({ error: (e as Error).message });
                }
              }}
            >
              ⤓ Report
            </Btn>
          )}
          <Btn
            aria-pressed={presentation}
            title="Presentation mode (p): larger text, builder hidden"
            onClick={() => setPresentation(!presentation)}
          >
            {presentation ? "◱ Exit present" : "◲ Present"}
          </Btn>
          <Btn title="Command palette" onClick={() => useUi.getState().setPalette(true)}>
            ⌘K
          </Btn>
          <Btn
            tone={demoStep === null ? "default" : "primary"}
            disabled={apiDown || sim.busy}
            onClick={() => void goToStep(0, true)}
          >
            ▶ Guided demo
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

      <div
        className={`grid min-h-0 flex-1 ${
          presentation && running
            ? "grid-cols-[minmax(0,1fr)_minmax(420px,40%)]"
            : "grid-cols-[280px_minmax(0,1fr)_430px]"
        }`}
      >
        {!(presentation && running) && (
          <aside className="min-h-0 border-r border-line bg-panel" aria-label="Scenario">
            {running ? <RunSidebar /> : <Builder />}
          </aside>
        )}

        <main className="relative flex min-h-0 min-w-0 flex-col bg-bg p-2">
          <div className="relative min-h-0 flex-1">
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
              <div className="absolute top-1 left-1 rounded-md border border-accent bg-panel/90 px-2 py-1 text-xs">
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
              <div className="absolute right-1 bottom-1 rounded-md border border-line bg-panel/90 px-2 py-1 font-mono text-xs text-dim">
                ({hover[0]}, {hover[1]}) {cellName(hover)}
                {view.state.hot.some((h) => key(h) === key(hover)) ? " · hot" : ""}
              </div>
            )}
          </div>
          <Legend running={running} />
        </main>

        <aside
          className="flex min-h-0 flex-col border-l border-line bg-panel"
          aria-label="Analysis"
        >
          <Tabs.Root
            value={tab}
            onValueChange={(v) => setTab(v as Tab)}
            className="flex min-h-0 flex-1 flex-col"
          >
            <Tabs.List className="flex border-b border-line" aria-label="Analysis panels">
              {TABS.map(([id, text]) => (
                <Tabs.Trigger
                  key={id}
                  value={id}
                  className="flex-1 border-b-2 border-transparent px-1 py-2.5 text-xs text-dim data-[state=active]:border-accent data-[state=active]:text-ink"
                >
                  {text}
                </Tabs.Trigger>
              ))}
            </Tabs.List>
            <Tabs.Content value="reasoning" className="min-h-0 flex-1">
              <ReasoningPanel />
            </Tabs.Content>
            <Tabs.Content value="search" className="min-h-0 flex-1">
              <SearchPanel />
            </Tabs.Content>
            <Tabs.Content value="planning" className="min-h-0 flex-1">
              <PlanningPanel />
            </Tabs.Content>
            <Tabs.Content value="uncertainty" className="min-h-0 flex-1">
              <UncertaintyPanel />
            </Tabs.Content>
            <Tabs.Content value="optimize" className="min-h-0 flex-1">
              <OptimizePanel />
            </Tabs.Content>
            <Tabs.Content value="agent" className="min-h-0 flex-1">
              <AgentPanel />
            </Tabs.Content>
            <Tabs.Content value="syllabus" className="min-h-0 flex-1">
              <SyllabusPanel />
            </Tabs.Content>
          </Tabs.Root>
        </aside>
      </div>

      <footer className="grid h-[190px] grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)] border-t border-line bg-panel">
        <div className="min-w-0 overflow-y-auto border-r border-line">
          <Controls />
        </div>
        <div className="min-h-0 min-w-0">
          <EventLog />
        </div>
      </footer>
      <ExplainDialog />
      <CommandPalette />
    </div>
  );
}

function Legend({ running }: { running: boolean }) {
  return (
    <div className="flex flex-wrap gap-x-3 pt-1.5 text-[11px] text-dim">
      <span>▦ wall</span>
      <span>▨ rubble</span>
      <span>♨ fire</span>
      <span>╱ hot zone (+4)</span>
      <span>☺ person</span>
      <span>⇥ exit</span>
      <span>◈ agent</span>
      {running && <span>- - route</span>}
    </div>
  );
}

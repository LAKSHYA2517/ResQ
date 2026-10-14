import { useQuery } from "@tanstack/react-query";
import {
  BrickWall,
  Check,
  DoorClosed,
  DoorOpen,
  Droplet,
  Flame,
  type LucideIcon,
  Pause,
  Play,
  RotateCcw,
  Route,
  Shovel,
  StepForward,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, type EventTypeName } from "../api/client";
import { useSim, useView } from "../store/sim";
import { Btn } from "./ui";

const SPEEDS = [1, 2, 4, 8, 16];

const PICKS: { type: EventTypeName; label: string; icon: LucideIcon }[] = [
  { type: "NEW_FIRE", label: "Fire", icon: Flame },
  { type: "FIRE_EXTINGUISHED", label: "Extinguish", icon: Droplet },
  { type: "OBSTACLE_ADDED", label: "Obstacle", icon: BrickWall },
  { type: "OBSTACLE_REMOVED", label: "Clear", icon: Shovel },
];

const sep = <span className="mx-1 h-5 w-px bg-line" aria-hidden />;

/** The media-style toolbar under the grid: playback, timeline, then hazard tools. */
export function Controls() {
  const sim = useSim();
  const view = useView();
  const head = sim.head;
  if (!head || !view) return null;
  const live = sim.viewTick === null;
  const done = head.finished;
  const blocked = !live || sim.busy;

  return (
    <div className="flex flex-col gap-1.5 border-t border-line bg-panel px-3 py-2">
      <div className="flex items-center gap-1.5">
        {sim.running ? (
          <Btn tone="primary" className="w-24" onClick={() => sim.setRunning(false)}>
            <Pause size={15} /> Pause
          </Btn>
        ) : (
          <Btn
            tone="primary"
            className="w-24"
            disabled={done || sim.busy}
            onClick={() => sim.setRunning(true)}
          >
            {done ? (
              <>
                <Check size={15} /> Finished
              </>
            ) : (
              <>
                <Play size={15} /> {head.tick === 0 ? "Start" : "Resume"}
              </>
            )}
          </Btn>
        )}
        <Btn disabled={done || sim.running || blocked} onClick={() => void sim.step()}>
          <StepForward size={15} /> Step
        </Btn>
        <Btn disabled={sim.busy} onClick={() => void sim.reset()}>
          <RotateCcw size={15} /> Reset
        </Btn>
        {sep}
        <input
          type="range"
          aria-label="Timeline"
          className="min-w-0 flex-1 accent-[var(--color-accent)]"
          min={0}
          max={head.tick}
          value={sim.viewTick ?? head.tick}
          disabled={head.tick === 0}
          onChange={(e) => void sim.scrub(Number(e.target.value))}
        />
        {live ? (
          <span className="w-12 text-xs font-semibold text-go">LIVE</span>
        ) : (
          <Btn onClick={() => void sim.scrub(null)}>Back to live ({head.tick})</Btn>
        )}
        <label className="flex items-center gap-1 text-xs text-dim">
          Speed
          <select
            className="rounded-md border border-line bg-panel px-1 py-1 text-sm text-ink"
            value={sim.speed}
            onChange={(e) => sim.setSpeed(Number(e.target.value))}
          >
            {SPEEDS.map((s) => (
              <option key={s} value={s}>
                {s}×
              </option>
            ))}
          </select>
        </label>
      </div>
      {live ? (
        <EventInjector disabled={blocked || done} />
      ) : (
        <p className="py-1 text-xs text-warn">
          Viewing tick {sim.viewTick} read-only, rebuilt from the event log.
        </p>
      )}
    </div>
  );
}

function EventInjector({ disabled }: { disabled: boolean }) {
  const { inject, pick, setPick } = useSim();
  const head = useSim((s) => s.head);
  const exits = head?.state.exits ?? [];
  const route = head?.route ?? [];
  const exitRef = useRef<HTMLSelectElement>(null);

  useEffect(() => {
    if (!pick) return;
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setPick(null);
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [pick, setPick]);

  return (
    <fieldset className="flex flex-wrap items-center gap-0.5 border-0 p-0 [&_button]:px-2">
      <legend className="sr-only">Event injector</legend>
      {PICKS.map((p) => (
        <Btn
          key={p.type}
          tone="ghost"
          disabled={disabled}
          aria-pressed={pick === p.type}
          title={`Click a cell to add: ${p.label.toLowerCase()}`}
          className={pick === p.type ? "!border-accent !bg-accent/10 !text-accent" : ""}
          onClick={() => setPick(pick === p.type ? null : p.type)}
        >
          <p.icon size={15} /> {p.label}
        </Btn>
      ))}
      <Btn
        tone="ghost"
        disabled={disabled || route.length < 4}
        aria-label="Fire on route"
        title="Light a fire two cells ahead on the current route"
        onClick={() => {
          const cell = route[2];
          if (cell) void inject("NEW_FIRE", { pos: cell });
        }}
      >
        <Route size={15} /> On route
      </Btn>
      {sep}
      <select
        ref={exitRef}
        aria-label="Exit to block or reopen"
        className="rounded-md border border-line bg-panel px-1 py-1 text-sm"
      >
        {exits.map((e) => (
          <option key={e.id} value={e.id}>
            {e.id}
            {e.available ? "" : " (blocked)"}
          </option>
        ))}
      </select>
      <Btn
        tone="ghost"
        disabled={disabled || exits.length === 0}
        onClick={() => void inject("EXIT_BLOCKED", { exit: exitRef.current?.value })}
      >
        <DoorClosed size={15} /> Block
      </Btn>
      <Btn
        tone="ghost"
        disabled={disabled || exits.length === 0}
        onClick={() => void inject("EXIT_REOPENED", { exit: exitRef.current?.value })}
      >
        <DoorOpen size={15} /> Reopen
      </Btn>
      {pick && <span className="ml-1 text-xs text-accent">Click a cell · Esc cancels</span>}
    </fieldset>
  );
}

const KIND_STYLE: Record<string, string> = {
  event: "text-warn",
  rejected: "text-bad",
  spread: "text-bad/80",
  status: "text-go",
  action: "text-go",
  replan: "text-warn font-semibold",
  plan: "text-accent",
  stuck: "text-bad",
};

export function EventLog() {
  const sessionId = useSim((s) => s.sessionId);
  const rev = useSim((s) => s.rev);
  const scrub = useSim((s) => s.scrub);
  const end = useRef<HTMLDivElement>(null);
  const [spread, setSpread] = useState(false);
  const log = useQuery({
    queryKey: ["log", sessionId, rev],
    queryFn: () => api.log(sessionId ?? ""),
    enabled: !!sessionId,
    placeholderData: (prev) => prev,
  });
  const entries = log.data?.filter((e) => spread || e.kind !== "spread");

  useEffect(() => {
    if (entries) end.current?.scrollIntoView({ block: "nearest" });
  }, [entries]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between px-3 pt-3">
        <h3 className="text-[13px] font-semibold text-ink">Event log</h3>
        <label className="flex items-center gap-1.5 text-xs text-dim">
          <input type="checkbox" checked={spread} onChange={(e) => setSpread(e.target.checked)} />
          fire spread
        </label>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-1 font-mono text-xs">
        {!entries?.length && <p className="text-dim">Nothing has happened yet.</p>}
        {entries?.map((e, i) => (
          <button
            // biome-ignore lint/suspicious/noArrayIndexKey: the log is append-only per tick
            key={`${e.tick}-${i}`}
            type="button"
            onClick={() => void scrub(e.tick)}
            className="block w-full py-0.5 text-left hover:bg-raised"
          >
            <span className="mr-2 text-dim">t{e.tick}</span>
            <span className={KIND_STYLE[e.kind] ?? ""}>{e.text}</span>
            {e.reason && <span className="block pl-7 text-warn">{e.reason}</span>}
          </button>
        ))}
        <div ref={end} />
      </div>
    </div>
  );
}

import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, type EventTypeName } from "../api/client";
import { useSim, useView } from "../store/sim";
import { Btn, Chip } from "./ui";

const SPEEDS = [1, 2, 4, 8, 16];

const PICKS: { type: EventTypeName; label: string }[] = [
  { type: "NEW_FIRE", label: "🔥 New fire" },
  { type: "FIRE_EXTINGUISHED", label: "💧 Extinguish" },
  { type: "OBSTACLE_ADDED", label: "🧱 Obstacle" },
  { type: "OBSTACLE_REMOVED", label: "⛏ Clear" },
];

export function Controls() {
  const sim = useSim();
  const view = useView();
  const head = sim.head;
  if (!head || !view) {
    return <div className="p-3 text-sm text-dim">Build or load a scenario, then start it.</div>;
  }
  const live = sim.viewTick === null;
  const done = head.finished;
  const blocked = !live || sim.busy;

  return (
    <div className="flex flex-col gap-2 p-3">
      <div className="flex flex-wrap items-center gap-2">
        {sim.running ? (
          <Btn tone="primary" onClick={() => sim.setRunning(false)}>
            ⏸ Pause
          </Btn>
        ) : (
          <Btn tone="primary" disabled={done || sim.busy} onClick={() => sim.setRunning(true)}>
            {done ? "✓ Finished" : head.tick === 0 ? "▶ Start" : "▶ Resume"}
          </Btn>
        )}
        <Btn disabled={done || sim.running || blocked} onClick={() => void sim.step()}>
          ⏭ Step
        </Btn>
        <Btn disabled={sim.busy} onClick={() => void sim.reset()}>
          ↺ Reset
        </Btn>
        <label className="flex items-center gap-1 text-xs text-dim">
          Speed
          <select
            className="rounded-md border border-line bg-raised px-1.5 py-1 text-sm text-ink"
            value={sim.speed}
            onChange={(e) => sim.setSpeed(Number(e.target.value))}
          >
            {SPEEDS.map((s) => (
              <option key={s} value={s}>
                {s}×/s
              </option>
            ))}
          </select>
        </label>
        <Chip
          tone={view.status === "complete" ? "go" : view.status === "stuck" ? "warn" : "accent"}
        >
          tick {view.tick} · {view.status}
        </Chip>
        <Chip>
          rescued {view.metrics.rescued}/{view.state.people.length}
        </Chip>
      </div>

      <div className="flex items-center gap-3">
        <input
          type="range"
          aria-label="Timeline"
          className="flex-1 accent-cyan-400"
          min={0}
          max={head.tick}
          value={sim.viewTick ?? head.tick}
          disabled={head.tick === 0}
          onChange={(e) => void sim.scrub(Number(e.target.value))}
        />
        {live ? (
          <Chip tone="go">LIVE</Chip>
        ) : (
          <Btn onClick={() => void sim.scrub(null)}>Back to live ({head.tick})</Btn>
        )}
      </div>
      {!live && (
        <p className="text-xs text-warn">
          Viewing tick {sim.viewTick} read-only, rebuilt from the event log.
        </p>
      )}

      <EventInjector disabled={blocked || done} />
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
    <fieldset className="flex flex-wrap items-center gap-1.5 border-0 p-0">
      <legend className="sr-only">Event injector</legend>
      <span className="text-xs text-dim">Inject:</span>
      {PICKS.map((p) => (
        <Btn
          key={p.type}
          disabled={disabled}
          className={pick === p.type ? "border-warn text-warn" : ""}
          onClick={() => setPick(pick === p.type ? null : p.type)}
        >
          {p.label}
        </Btn>
      ))}
      <Btn
        disabled={disabled || route.length < 4}
        title="Light a fire two cells ahead on the current route"
        onClick={() => {
          const cell = route[2];
          if (cell) void inject("NEW_FIRE", { pos: cell });
        }}
      >
        🔥 On route
      </Btn>
      <select
        ref={exitRef}
        aria-label="Exit to block or reopen"
        className="rounded-md border border-line bg-raised px-1.5 py-1 text-sm"
      >
        {exits.map((e) => (
          <option key={e.id} value={e.id}>
            {e.id}
            {e.available ? "" : " (blocked)"}
          </option>
        ))}
      </select>
      <Btn
        disabled={disabled || exits.length === 0}
        onClick={() => void inject("EXIT_BLOCKED", { exit: exitRef.current?.value })}
      >
        ⛔ Block exit
      </Btn>
      <Btn
        disabled={disabled || exits.length === 0}
        onClick={() => void inject("EXIT_REOPENED", { exit: exitRef.current?.value })}
      >
        ✔ Reopen
      </Btn>
      {pick && (
        <span className="text-xs text-warn">
          Click a cell on the grid to apply {pick} (Esc cancels)
        </span>
      )}
    </fieldset>
  );
}

const KIND_STYLE: Record<string, string> = {
  event: "text-warn",
  rejected: "text-bad",
  spread: "text-orange-300",
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
      <div className="flex items-center justify-between px-3 pt-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-dim">Event log</h3>
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
            {e.reason && <span className="block pl-7 text-warn">↳ {e.reason}</span>}
          </button>
        ))}
        <div ref={end} />
      </div>
    </div>
  );
}

import * as Dialog from "@radix-ui/react-dialog";
import { useEffect, useRef, useState } from "react";
import type { Compare, GridState, SearchRun } from "../api/client";
import { key } from "../lib/cells";
import { COLORS } from "../lib/draw";
import { Btn, Chip, fmt } from "./ui";

const SIZE = 190;

/** One small board: cells light up in the order the engine expanded them. */
function Board({ state, run, shown }: { state: GridState; run: SearchRun; shown: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const done = shown >= run.expanded;

  useEffect(() => {
    const el = ref.current;
    const ctx = el?.getContext("2d");
    if (!el || !ctx) return;
    const dpr = window.devicePixelRatio || 1;
    el.width = SIZE * dpr;
    el.height = SIZE * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const s = Math.floor(SIZE / Math.max(state.rows, state.cols));
    const fire = new Set(state.fire.map(key));
    const hot = new Set(state.hot.map(key));
    ctx.clearRect(0, 0, SIZE, SIZE);
    for (let r = 0; r < state.rows; r++) {
      for (let c = 0; c < state.cols; c++) {
        const kind = state.terrain[r]?.[c];
        ctx.fillStyle =
          kind === "wall" ? COLORS.wall : kind === "rubble" ? COLORS.rubble : COLORS.floor;
        if (hot.has(`${r},${c}`)) ctx.fillStyle = "#f3d9b8";
        if (fire.has(`${r},${c}`)) ctx.fillStyle = COLORS.fire;
        ctx.fillRect(c * s, r * s, s - 1, s - 1);
      }
    }
    const n = run.expansion_order.length;
    run.expansion_order.slice(0, shown).forEach((cell, i) => {
      ctx.fillStyle = `hsla(${215 - 175 * (n > 1 ? i / (n - 1) : 0)}, 70%, 55%, 0.45)`;
      ctx.fillRect(cell[1] * s + 1, cell[0] * s + 1, s - 3, s - 3);
    });
    if (done && run.path.length > 1) {
      ctx.strokeStyle = COLORS.route;
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      run.path.forEach((cell, i) => {
        const x = (cell[1] + 0.5) * s;
        const y = (cell[0] + 0.5) * s;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
    }
  }, [state, run, shown, done]);

  return (
    <figure className="rounded-md border border-line bg-bg p-2">
      <figcaption className="mb-1 flex items-center justify-between text-xs">
        <span className="font-semibold">
          {run.label.replace("astar", "A*").replace("+", " · ")}
        </span>
        {done ? (
          !run.found ? (
            <Chip tone="bad">no route</Chip>
          ) : run.optimal_vs_ucs ? (
            <Chip tone="go">✓ optimal</Chip>
          ) : (
            <Chip tone="warn">✗ costlier</Chip>
          )
        ) : (
          <Chip tone="accent">searching</Chip>
        )}
      </figcaption>
      <canvas
        ref={ref}
        style={{ width: SIZE, height: SIZE }}
        role="img"
        aria-label={`${run.label}: ${Math.min(shown, run.expanded)} of ${run.expanded} cells expanded`}
      />
      <dl className="mt-1 grid grid-cols-3 gap-1 text-center text-[11px] text-dim">
        <div>
          <dt>expanded</dt>
          <dd className="text-sm text-ink tabular-nums">
            {Math.min(shown, run.expanded)}
            <span className="text-dim">/{run.expanded}</span>
          </dd>
        </div>
        <div>
          <dt>cost</dt>
          <dd className="text-sm text-ink tabular-nums">{done ? fmt(run.cost) : "…"}</dd>
        </div>
        <div>
          <dt>steps</dt>
          <dd className="text-sm text-ink tabular-nums">{done && run.found ? run.steps : "…"}</dd>
        </div>
      </dl>
    </figure>
  );
}

/** Algorithm Race: every run replays its real expansion order at the same pace. */
export function RaceDialog({
  result,
  state,
  onClose,
}: {
  result: Compare;
  state: GridState;
  onClose: () => void;
}) {
  const longest = Math.max(1, ...result.runs.map((r) => r.expanded));
  const [shown, setShown] = useState(0);
  const [lap, setLap] = useState(0);

  // biome-ignore lint/correctness/useExhaustiveDependencies: `lap` restarts the race on purpose
  useEffect(() => {
    setShown(0);
    const step = Math.max(1, Math.ceil(longest / 160));
    const id = setInterval(() => setShown((n) => (n >= longest ? n : n + step)), 40);
    return () => clearInterval(id);
  }, [longest, lap]);

  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/70" />
        <Dialog.Content className="fixed top-1/2 left-1/2 z-50 max-h-[92vh] w-[min(1180px,96vw)] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-lg border border-line bg-panel p-5">
          <div className="mb-3 flex items-center gap-3">
            <Dialog.Title className="text-lg font-semibold">Algorithm race</Dialog.Title>
            <Dialog.Description className="flex-1 text-sm text-dim">
              Agent ({result.source.join(", ")}) → {result.target_id} ({result.goal.join(", ")}),
              tick {result.tick}. Same problem, same pace: one cell per step of each run's real
              expansion order.
            </Dialog.Description>
            <Btn onClick={() => setLap(lap + 1)}>↺ Replay</Btn>
            <Dialog.Close asChild>
              <Btn>Close</Btn>
            </Dialog.Close>
          </div>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(210px,1fr))] gap-3">
            {result.runs.map((r) => (
              <Board key={r.label} state={state} run={r} shown={shown} />
            ))}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

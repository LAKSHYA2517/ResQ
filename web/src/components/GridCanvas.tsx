import { useEffect, useRef } from "react";
import type { Cell } from "../api/client";
import { cellAt, drawScene, fitLayout, type Layout, type Scene } from "../lib/draw";

export type Pointer = "down" | "move" | "up";

interface Props {
  scene: Scene;
  label: string;
  onCell?: (cell: Cell, phase: Pointer) => void;
  onHover?: (cell: Cell | null) => void;
  cursor?: string;
}

const GLIDE_MS = 240;

/** Draws the grid and animates it. Scene data is read through a ref so the render loop is
 * created once; React re-renders only update what the loop sees. */
export function GridCanvas({ scene, label, onCell, onHover, cursor }: Props) {
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const live = useRef(scene);
  live.current = scene;
  const layout = useRef<Layout>({ cell: 0, ox: 0, oy: 0 });
  const painting = useRef(false);
  const glide = useRef<{ from: Cell; to: Cell; at: number; facing: number } | null>(null);

  useEffect(() => {
    const el = canvas.current;
    const box = wrap.current;
    if (!el || !box) return;
    const ctx = el.getContext("2d");
    if (!ctx) return;
    let raf = 0;
    let w = 0;
    let h = 0;
    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      w = box.clientWidth;
      h = box.clientHeight;
      el.width = Math.floor(w * dpr);
      el.height = Math.floor(h * dpr);
      el.style.width = `${w}px`;
      el.style.height = `${h}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(box);
    resize();

    const t0 = performance.now();
    let revealed = { id: "", at: 0 };
    const frame = (now: number) => {
      const sc = live.current;
      const { rows, cols, agent } = sc.state;
      layout.current = fitLayout(w, h, rows, cols);

      // agent glide between ticks
      const g = glide.current;
      if (!g || g.to[0] !== agent.pos[0] || g.to[1] !== agent.pos[1]) {
        const from: Cell = g ? currentPos(g, now) : agent.pos;
        const dr = agent.pos[0] - from[0];
        const dc = agent.pos[1] - from[1];
        glide.current = {
          from,
          to: agent.pos,
          at: now,
          facing: dr || dc ? Math.atan2(dr, dc) : (g?.facing ?? 0),
        };
      }
      const cur = glide.current;
      const pos = cur ? currentPos(cur, now) : agent.pos;

      // explored cells fade in progressively whenever a new run is selected
      const id = `${sc.explored.length}:${sc.explored[0]?.join(",") ?? ""}`;
      if (revealed.id !== id) revealed = { id, at: now };
      const shown = sc.motion
        ? Math.min(sc.explored.length, ((now - revealed.at) / 900) * sc.explored.length)
        : sc.explored.length;

      drawScene(
        ctx,
        { ...sc, exploredShown: Math.ceil(shown) },
        layout.current,
        (now - t0) / 1000,
        { pos: pos as [number, number], facing: cur?.facing ?? 0 },
      );
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => {
      cancelAnimationFrame(raf);
      observer.disconnect();
    };
  }, []);

  const toCell = (e: React.PointerEvent): Cell | null => {
    const rect = canvas.current?.getBoundingClientRect();
    if (!rect) return null;
    const { rows, cols } = live.current.state;
    return cellAt(layout.current, e.clientX - rect.left, e.clientY - rect.top, rows, cols);
  };

  return (
    <div ref={wrap} className="relative h-full w-full">
      <canvas
        ref={canvas}
        role="img"
        aria-label={label}
        className="block touch-none"
        style={{ cursor: cursor ?? "default" }}
        onPointerDown={(e) => {
          const cell = toCell(e);
          if (!cell || !onCell) return;
          painting.current = true;
          e.currentTarget.setPointerCapture(e.pointerId);
          onCell(cell, "down");
        }}
        onPointerMove={(e) => {
          const cell = toCell(e);
          onHover?.(cell);
          if (painting.current && cell && onCell) onCell(cell, "move");
        }}
        onPointerUp={(e) => {
          if (!painting.current) return;
          painting.current = false;
          const cell = toCell(e);
          if (cell && onCell) onCell(cell, "up");
        }}
        onPointerLeave={() => onHover?.(null)}
      />
    </div>
  );
}

function currentPos(g: { from: Cell; to: Cell; at: number }, now: number): Cell {
  const t = Math.min(1, (now - g.at) / GLIDE_MS);
  const e = 1 - (1 - t) ** 3;
  return [g.from[0] + (g.to[0] - g.from[0]) * e, g.from[1] + (g.to[1] - g.from[1]) * e];
}

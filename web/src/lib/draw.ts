/** Canvas 2D drawing for the grid. Everything drawn comes from engine data passed in `Scene`;
 * nothing here decides routes, hazards or outcomes. */

import type { Cell, GridState } from "../api/client";
import { key } from "./cells";

export interface Scene {
  state: GridState;
  route: Cell[];
  waypoints: { cell: Cell; label: string }[];
  trail: Cell[];
  explored: Cell[]; // expansion order of the selected search run
  exploredShown: number; // how many of them are revealed (animated by the caller)
  targetId: string | null;
  issues: Cell[]; // builder validation problems
  highlight: Cell[]; // provenance / log selection
  hover: Cell | null;
  pickMode: boolean;
  motion: boolean;
}

export interface Layout {
  cell: number;
  ox: number;
  oy: number;
}

export const COLORS = {
  bg: "#0a1017",
  floor: "#131c27",
  grid: "#223246",
  wall: "#56657a",
  wallLine: "#2b3544",
  rubble: "#3a2e20",
  rubbleLine: "#c79a5b",
  hot: "#ffa733",
  fire: "#ff4d2e",
  fireCore: "#ffd23f",
  exit: "#0c4a2a",
  exitEdge: "#4ade80",
  agent: "#22d3ee",
  route: "#fde047",
  target: "#fde047",
  issue: "#ff2d55",
  status: { WAITING: "#38bdf8", CARRIED: "#c4b5fd", EVACUATED: "#4ade80", TRAPPED: "#f87171" },
} as const;

export function fitLayout(w: number, h: number, rows: number, cols: number): Layout {
  const cell = Math.max(8, Math.floor(Math.min(w / cols, h / rows)));
  return { cell, ox: Math.floor((w - cell * cols) / 2), oy: Math.floor((h - cell * rows) / 2) };
}

export function cellAt(
  layout: Layout,
  x: number,
  y: number,
  rows: number,
  cols: number,
): Cell | null {
  const c = Math.floor((x - layout.ox) / layout.cell);
  const r = Math.floor((y - layout.oy) / layout.cell);
  return r >= 0 && r < rows && c >= 0 && c < cols ? [r, c] : null;
}

const center = (l: Layout, [r, c]: Cell): [number, number] => [
  l.ox + (c + 0.5) * l.cell,
  l.oy + (r + 0.5) * l.cell,
];

function hatch(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  s: number,
  color: string,
  gap: number,
  dir: 1 | -1,
  width = 1.5,
) {
  ctx.save();
  ctx.beginPath();
  ctx.rect(x, y, s, s);
  ctx.clip();
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.beginPath();
  for (let d = -s; d < 2 * s; d += gap) {
    if (dir === 1) {
      ctx.moveTo(x + d, y + s);
      ctx.lineTo(x + d + s, y);
    } else {
      ctx.moveTo(x + d, y);
      ctx.lineTo(x + d + s, y + s);
    }
  }
  ctx.stroke();
  ctx.restore();
}

/** Rubble: scattered stones, so it reads differently from the hot zone's diagonal stripes. */
function stones(ctx: CanvasRenderingContext2D, x: number, y: number, s: number, seed: number) {
  ctx.fillStyle = COLORS.rubbleLine;
  for (let i = 0; i < 7; i++) {
    const a = Math.sin(seed * 12.9898 + i * 78.233) * 43758.5453;
    const b = Math.sin(seed * 39.346 + i * 11.135) * 24634.6345;
    const px = x + s * (0.12 + 0.76 * (a - Math.floor(a)));
    const py = y + s * (0.12 + 0.76 * (b - Math.floor(b)));
    const size = s * (0.05 + 0.05 * ((i * 37) % 3));
    ctx.beginPath();
    ctx.moveTo(px - size, py + size * 0.6);
    ctx.lineTo(px - size * 0.3, py - size);
    ctx.lineTo(px + size, py - size * 0.2);
    ctx.lineTo(px + size * 0.5, py + size);
    ctx.closePath();
    ctx.fill();
  }
}

function bricks(ctx: CanvasRenderingContext2D, x: number, y: number, s: number) {
  ctx.strokeStyle = COLORS.wallLine;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  const rows = 3;
  for (let i = 1; i < rows; i++) {
    ctx.moveTo(x, y + (s * i) / rows);
    ctx.lineTo(x + s, y + (s * i) / rows);
  }
  for (let i = 0; i < rows; i++) {
    const off = i % 2 === 0 ? s * 0.33 : s * 0.66;
    ctx.moveTo(x + off, y + (s * i) / rows);
    ctx.lineTo(x + off, y + (s * (i + 1)) / rows);
  }
  ctx.stroke();
}

function flame(
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  s: number,
  t: number,
  seed: number,
) {
  const flick = Math.sin(t * 7 + seed * 1.7) * 0.08 + Math.sin(t * 13 + seed) * 0.05;
  const h = s * (0.42 + flick);
  const w = s * 0.26;
  ctx.fillStyle = COLORS.fire;
  ctx.beginPath();
  ctx.moveTo(cx, cy - h);
  ctx.bezierCurveTo(cx + w * 1.3, cy - h * 0.2, cx + w, cy + h * 0.7, cx, cy + h * 0.7);
  ctx.bezierCurveTo(cx - w, cy + h * 0.7, cx - w * 1.3, cy - h * 0.2, cx, cy - h);
  ctx.fill();
  ctx.fillStyle = COLORS.fireCore;
  ctx.beginPath();
  ctx.moveTo(cx, cy - h * 0.2);
  ctx.bezierCurveTo(cx + w * 0.7, cy + h * 0.1, cx + w * 0.5, cy + h * 0.65, cx, cy + h * 0.65);
  ctx.bezierCurveTo(cx - w * 0.5, cy + h * 0.65, cx - w * 0.7, cy + h * 0.1, cx, cy - h * 0.2);
  ctx.fill();
}

function pictogram(
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  s: number,
  color: string,
) {
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(cx, cy - s * 0.14, s * 0.1, 0, Math.PI * 2);
  ctx.fill();
  ctx.beginPath();
  ctx.moveTo(cx - s * 0.17, cy + s * 0.2);
  ctx.quadraticCurveTo(cx, cy - s * 0.12, cx + s * 0.17, cy + s * 0.2);
  ctx.closePath();
  ctx.fill();
}

function badge(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  r: number,
  status: GridState["people"][number]["status"],
) {
  ctx.fillStyle = "#0a1017";
  ctx.beginPath();
  ctx.arc(x, y, r + 1.5, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = COLORS.status[status];
  ctx.strokeStyle = COLORS.status[status];
  ctx.lineWidth = Math.max(1.5, r * 0.28);
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  if (status === "TRAPPED") {
    ctx.beginPath();
    ctx.moveTo(x, y - r);
    ctx.lineTo(x + r, y + r * 0.8);
    ctx.lineTo(x - r, y + r * 0.8);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = "#0a1017";
    ctx.fillRect(x - r * 0.12, y - r * 0.3, r * 0.24, r * 0.55);
  } else if (status === "EVACUATED") {
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "#0a1017";
    ctx.beginPath();
    ctx.moveTo(x - r * 0.5, y);
    ctx.lineTo(x - r * 0.1, y + r * 0.45);
    ctx.lineTo(x + r * 0.55, y - r * 0.4);
    ctx.stroke();
  } else if (status === "CARRIED") {
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "#0a1017";
    ctx.beginPath();
    ctx.moveTo(x, y + r * 0.5);
    ctx.lineTo(x, y - r * 0.5);
    ctx.moveTo(x - r * 0.4, y - r * 0.1);
    ctx.lineTo(x, y - r * 0.55);
    ctx.lineTo(x + r * 0.4, y - r * 0.1);
    ctx.stroke();
  } else {
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#0a1017";
    ctx.beginPath();
    ctx.arc(x, y, r * 0.35, 0, Math.PI * 2);
    ctx.fill();
  }
}

export function drawScene(
  ctx: CanvasRenderingContext2D,
  scene: Scene,
  l: Layout,
  time: number,
  agent: { pos: [number, number]; facing: number },
) {
  const { state } = scene;
  const s = l.cell;
  ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
  const fire = new Set(state.fire.map(key));
  const hot = new Set(state.hot.map(key));
  const t = scene.motion ? time : 0;

  // terrain, hot zone, fire
  for (let r = 0; r < state.rows; r++) {
    for (let c = 0; c < state.cols; c++) {
      const x = l.ox + c * s;
      const y = l.oy + r * s;
      const kind = state.terrain[r]?.[c] ?? "floor";
      ctx.fillStyle = kind === "wall" ? COLORS.wall : kind === "exit" ? COLORS.exit : COLORS.floor;
      if (kind === "rubble") ctx.fillStyle = COLORS.rubble;
      ctx.fillRect(x, y, s, s);
      if (kind === "wall") bricks(ctx, x, y, s);
      if (kind === "rubble") stones(ctx, x, y, s, r * 7 + c);
      if (hot.has(`${r},${c}`)) {
        ctx.fillStyle = "rgba(255,167,51,0.22)";
        ctx.fillRect(x, y, s, s);
        hatch(ctx, x, y, s, COLORS.hot, Math.max(6, s / 5), -1, 2);
      }
      if (fire.has(`${r},${c}`)) {
        ctx.fillStyle = "rgba(255,77,46,0.32)";
        ctx.fillRect(x, y, s, s);
      }
      ctx.strokeStyle = COLORS.grid;
      ctx.lineWidth = 1;
      ctx.strokeRect(x + 0.5, y + 0.5, s - 1, s - 1);
    }
  }

  // explored heat (search run overlay)
  const n = scene.explored.length;
  for (let i = 0; i < Math.min(scene.exploredShown, n); i++) {
    const cell = scene.explored[i];
    if (!cell) continue;
    const tt = n > 1 ? i / (n - 1) : 0;
    ctx.fillStyle = `hsla(${230 - 200 * tt}, 95%, 58%, 0.42)`;
    ctx.fillRect(l.ox + cell[1] * s + 2, l.oy + cell[0] * s + 2, s - 4, s - 4);
  }

  // highlight + builder issues
  ctx.lineWidth = 3;
  for (const cell of scene.highlight) {
    ctx.strokeStyle = "#fff";
    ctx.setLineDash([]);
    ctx.strokeRect(l.ox + cell[1] * s + 2, l.oy + cell[0] * s + 2, s - 4, s - 4);
  }
  for (const cell of scene.issues) {
    ctx.strokeStyle = COLORS.issue;
    ctx.setLineDash([5, 4]);
    ctx.strokeRect(l.ox + cell[1] * s + 2, l.oy + cell[0] * s + 2, s - 4, s - 4);
  }
  ctx.setLineDash([]);

  // fire glyphs
  for (const [r, c] of state.fire) flame(ctx, ...center(l, [r, c]), s, t, r * 31 + c);

  // exits: door glyph; X when unusable
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  for (const e of state.exits) {
    const [cx, cy] = center(l, e.pos);
    const ok = e.available && e.usable;
    ctx.strokeStyle = ok ? COLORS.exitEdge : "#f87171";
    ctx.lineWidth = 2;
    ctx.strokeRect(cx - s * 0.3, cy - s * 0.34, s * 0.6, s * 0.68);
    ctx.fillStyle = ok ? COLORS.exitEdge : "#f87171";
    ctx.font = `bold ${Math.max(9, s * 0.2)}px ui-sans-serif, system-ui`;
    ctx.fillText(e.id.toUpperCase(), cx, cy - s * 0.04);
    ctx.fillRect(cx + s * 0.1, cy + s * 0.12, s * 0.07, s * 0.07);
    if (!ok) {
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(cx - s * 0.3, cy - s * 0.34);
      ctx.lineTo(cx + s * 0.3, cy + s * 0.34);
      ctx.moveTo(cx + s * 0.3, cy - s * 0.34);
      ctx.lineTo(cx - s * 0.3, cy + s * 0.34);
      ctx.stroke();
    }
  }

  // trail
  ctx.fillStyle = "rgba(34,211,238,0.35)";
  for (const cell of scene.trail) {
    const [cx, cy] = center(l, cell);
    ctx.beginPath();
    ctx.arc(cx, cy, Math.max(2, s * 0.07), 0, Math.PI * 2);
    ctx.fill();
  }

  // route (animated dashes) with arrow head
  if (scene.route.length > 1) {
    ctx.strokeStyle = COLORS.route;
    ctx.lineWidth = Math.max(2.5, s * 0.08);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.setLineDash([s * 0.2, s * 0.14]);
    ctx.lineDashOffset = -t * s * 0.9;
    ctx.beginPath();
    scene.route.forEach((cell, i) => {
      const [cx, cy] = center(l, cell);
      if (i === 0) ctx.moveTo(cx, cy);
      else ctx.lineTo(cx, cy);
    });
    ctx.stroke();
    ctx.setLineDash([]);
    const a = scene.route[scene.route.length - 2];
    const b = scene.route[scene.route.length - 1];
    if (a && b) {
      const [bx, by] = center(l, b);
      const ang = Math.atan2(b[0] - a[0], b[1] - a[1]);
      ctx.fillStyle = COLORS.route;
      ctx.beginPath();
      ctx.moveTo(bx + Math.cos(ang) * s * 0.22, by + Math.sin(ang) * s * 0.22);
      ctx.lineTo(bx + Math.cos(ang + 2.5) * s * 0.2, by + Math.sin(ang + 2.5) * s * 0.2);
      ctx.lineTo(bx + Math.cos(ang - 2.5) * s * 0.2, by + Math.sin(ang - 2.5) * s * 0.2);
      ctx.fill();
    }
  }

  // plan waypoints
  for (const w of scene.waypoints) {
    const [cx, cy] = center(l, w.cell);
    const r = Math.max(8, s * 0.17);
    const x = cx + s * 0.3;
    const y = cy - s * 0.3;
    ctx.fillStyle = "#0a1017";
    ctx.strokeStyle = COLORS.route;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = COLORS.route;
    ctx.font = `bold ${Math.max(9, r * 1.1)}px ui-sans-serif, system-ui`;
    ctx.fillText(w.label, x, y + 0.5);
  }

  // people
  for (const p of state.people) {
    if (p.status === "EVACUATED" || p.status === "CARRIED") continue; // shown at the exit / on the agent
    const [cx, cy] = center(l, p.pos);
    const color = COLORS.status[p.status];
    ctx.fillStyle = "rgba(10,16,23,0.82)";
    ctx.strokeStyle = color;
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.arc(cx, cy, s * 0.32, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    pictogram(ctx, cx, cy, s, color);
    badge(ctx, cx + s * 0.3, cy + s * 0.3, Math.max(5, s * 0.13), p.status);
    ctx.fillStyle = "#e6edf5";
    ctx.font = `bold ${Math.max(10, s * 0.21)}px ui-sans-serif, system-ui`;
    ctx.fillText(p.id, cx, cy + s * 0.43);
    if (p.id === scene.targetId) {
      ctx.strokeStyle = COLORS.target;
      ctx.lineWidth = 2.5;
      ctx.setLineDash([6, 5]);
      ctx.lineDashOffset = -t * 20;
      ctx.beginPath();
      ctx.arc(cx, cy, s * 0.43 + Math.sin(t * 3) * 1.5, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash([]);
    }
  }
  for (const e of state.exits) {
    // evacuees queue as small ticks beside their exit
    const got = state.people.filter((p) => p.status === "EVACUATED" && key(p.pos) === key(e.pos));
    const [cx, cy] = center(l, e.pos);
    got.forEach((p, i) => {
      badge(ctx, cx - s * 0.3 + i * s * 0.2, cy + s * 0.34, Math.max(5, s * 0.12), "EVACUATED");
      ctx.fillStyle = "#e6edf5";
      ctx.font = `${Math.max(8, s * 0.15)}px ui-sans-serif, system-ui`;
      ctx.fillText(p.id, cx - s * 0.3 + i * s * 0.2, cy + s * 0.2);
    });
  }

  // agent (glides), chevron shows facing; carried person rides on top
  const ax = l.ox + (agent.pos[1] + 0.5) * s;
  const ay = l.oy + (agent.pos[0] + 0.5) * s;
  ctx.save();
  ctx.translate(ax, ay);
  ctx.fillStyle = "#06222a";
  ctx.strokeStyle = COLORS.agent;
  ctx.lineWidth = 3;
  const half = s * 0.3;
  ctx.beginPath();
  ctx.roundRect(-half, -half, half * 2, half * 2, s * 0.08);
  ctx.fill();
  ctx.stroke();
  ctx.rotate(agent.facing);
  ctx.fillStyle = COLORS.agent;
  ctx.beginPath();
  ctx.moveTo(half * 0.7, 0);
  ctx.lineTo(-half * 0.35, -half * 0.5);
  ctx.lineTo(-half * 0.1, 0);
  ctx.lineTo(-half * 0.35, half * 0.5);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
  if (state.agent.carrying) {
    pictogram(ctx, ax, ay - s * 0.38, s * 0.7, COLORS.status.CARRIED);
    ctx.fillStyle = COLORS.status.CARRIED;
    ctx.font = `bold ${Math.max(9, s * 0.18)}px ui-sans-serif, system-ui`;
    ctx.fillText(state.agent.carrying, ax, ay + s * 0.42);
  }

  // hover outline (builder / event pick)
  if (scene.hover) {
    ctx.strokeStyle = scene.pickMode ? COLORS.fire : "#ffffff";
    ctx.lineWidth = 2;
    ctx.strokeRect(l.ox + scene.hover[1] * s + 1, l.oy + scene.hover[0] * s + 1, s - 2, s - 2);
  }
}

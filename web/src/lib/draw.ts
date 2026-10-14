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
  bg: "#f5f3ed",
  floor: "#fbfaf7",
  grid: "#e3dfd4",
  wall: "#2f353d",
  rubble: "#efe9dc",
  rubbleLine: "#8a7a62",
  hot: "rgba(214,110,40,0.16)",
  fire: "#c8402c",
  fireCore: "#f0a24a",
  exit: "#e5f0e8",
  exitEdge: "#2b7a4b",
  blocked: "#b8322a",
  ink: "#1c2229",
  paper: "#ffffff",
  agent: "#1c2229",
  route: "#1f4fa3",
  target: "#1f4fa3",
  issue: "#b8322a",
  status: { WAITING: "#1f4fa3", CARRIED: "#6b4fa3", EVACUATED: "#2b7a4b", TRAPPED: "#b8322a" },
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

/** Rubble: a seeded stipple, so it reads as loose debris rather than a solid block. */
function stipple(ctx: CanvasRenderingContext2D, x: number, y: number, s: number, seed: number) {
  ctx.fillStyle = COLORS.rubbleLine;
  const r = Math.max(0.9, s * 0.03);
  for (let i = 0; i < 14; i++) {
    const a = Math.sin(seed * 12.9898 + i * 78.233) * 43758.5453;
    const b = Math.sin(seed * 39.346 + i * 11.135) * 24634.6345;
    ctx.beginPath();
    ctx.arc(
      x + s * (0.1 + 0.8 * (a - Math.floor(a))),
      y + s * (0.1 + 0.8 * (b - Math.floor(b))),
      r,
      0,
      Math.PI * 2,
    );
    ctx.fill();
  }
}

function flame(
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  s: number,
  t: number,
  seed: number,
) {
  const flick = Math.sin(t * 7 + seed * 1.7) * 0.05 + Math.sin(t * 13 + seed) * 0.03;
  const h = s * (0.32 + flick);
  const w = s * 0.2;
  ctx.fillStyle = COLORS.fire;
  ctx.beginPath();
  ctx.moveTo(cx, cy - h);
  ctx.bezierCurveTo(cx + w * 1.3, cy - h * 0.2, cx + w, cy + h * 0.7, cx, cy + h * 0.7);
  ctx.bezierCurveTo(cx - w, cy + h * 0.7, cx - w * 1.3, cy - h * 0.2, cx, cy - h);
  ctx.fill();
  ctx.fillStyle = COLORS.fireCore;
  ctx.beginPath();
  ctx.moveTo(cx, cy - h * 0.1);
  ctx.bezierCurveTo(cx + w * 0.6, cy + h * 0.15, cx + w * 0.45, cy + h * 0.62, cx, cy + h * 0.62);
  ctx.bezierCurveTo(cx - w * 0.45, cy + h * 0.62, cx - w * 0.6, cy + h * 0.15, cx, cy - h * 0.1);
  ctx.fill();
}

const font = (px: number, weight = 600) =>
  `${weight} ${px}px "Inter Variable", system-ui, sans-serif`;

/** A person: white disc, status-coloured ring, id inside. Trapped people get a filled disc so
 * they read at a glance from the back of a room. */
function marker(
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  r: number,
  id: string,
  status: GridState["people"][number]["status"],
) {
  const color = COLORS.status[status];
  const filled = status === "TRAPPED" || status === "EVACUATED";
  ctx.fillStyle = filled ? color : COLORS.paper;
  ctx.strokeStyle = color;
  ctx.lineWidth = Math.max(1.5, r * 0.16);
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = filled ? COLORS.paper : color;
  ctx.font = font(Math.max(9, r * 0.9));
  ctx.fillText(id, cx, cy + 0.5);
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
  const hot = new Set(state.hot.map(key));
  const t = scene.motion ? time : 0;
  const cellRect = ([r, c]: Cell, inset: number) =>
    [l.ox + c * s + inset, l.oy + r * s + inset, s - 2 * inset, s - 2 * inset] as const;

  // terrain: flat fills, hairline grid
  for (let r = 0; r < state.rows; r++) {
    for (let c = 0; c < state.cols; c++) {
      const x = l.ox + c * s;
      const y = l.oy + r * s;
      const kind = state.terrain[r]?.[c] ?? "floor";
      ctx.fillStyle =
        kind === "wall"
          ? COLORS.wall
          : kind === "exit"
            ? COLORS.exit
            : kind === "rubble"
              ? COLORS.rubble
              : COLORS.floor;
      ctx.fillRect(x, y, s, s);
      if (kind === "rubble") stipple(ctx, x, y, s, r * 7 + c);
      if (hot.has(`${r},${c}`)) {
        ctx.fillStyle = COLORS.hot;
        ctx.fillRect(x, y, s, s);
      }
    }
  }
  ctx.strokeStyle = COLORS.grid;
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let r = 0; r <= state.rows; r++) {
    ctx.moveTo(l.ox, l.oy + r * s + 0.5);
    ctx.lineTo(l.ox + state.cols * s, l.oy + r * s + 0.5);
  }
  for (let c = 0; c <= state.cols; c++) {
    ctx.moveTo(l.ox + c * s + 0.5, l.oy);
    ctx.lineTo(l.ox + c * s + 0.5, l.oy + state.rows * s);
  }
  ctx.stroke();
  ctx.strokeStyle = COLORS.ink;
  ctx.lineWidth = 1.5;
  ctx.strokeRect(l.ox, l.oy, state.cols * s, state.rows * s);

  // explored heat (search run overlay): blue early, amber late
  const n = scene.explored.length;
  for (let i = 0; i < Math.min(scene.exploredShown, n); i++) {
    const cell = scene.explored[i];
    if (!cell) continue;
    const tt = n > 1 ? i / (n - 1) : 0;
    ctx.fillStyle = `hsla(${215 - 175 * tt}, 70%, 55%, 0.28)`;
    ctx.fillRect(...cellRect(cell, 1));
  }

  // highlight + builder issues
  ctx.lineWidth = 2;
  ctx.strokeStyle = COLORS.ink;
  for (const cell of scene.highlight) ctx.strokeRect(...cellRect(cell, 2));
  ctx.strokeStyle = COLORS.issue;
  ctx.setLineDash([4, 3]);
  for (const cell of scene.issues) ctx.strokeRect(...cellRect(cell, 2));
  ctx.setLineDash([]);

  // fire
  for (const [r, c] of state.fire) flame(ctx, ...center(l, [r, c]), s, t, r * 31 + c);

  // exits: a door mark (leaf + swing arc) and the id; a slash when unusable
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  for (const e of state.exits) {
    const [x, y] = cellRect(e.pos, 0);
    const ok = e.available && e.usable;
    const color = ok ? COLORS.exitEdge : COLORS.blocked;
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(x + s * 0.2, y + s * 0.8);
    ctx.lineTo(x + s * 0.2, y + s * 0.25);
    ctx.stroke();
    ctx.lineWidth = 1;
    ctx.setLineDash([2, 2]);
    ctx.beginPath();
    ctx.arc(x + s * 0.2, y + s * 0.8, s * 0.55, -Math.PI / 2, 0);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = color;
    ctx.font = font(Math.max(9, s * 0.2), 700);
    ctx.fillText(e.id.toUpperCase(), x + s * 0.55, y + s * 0.62);
    if (!ok) {
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(x + s * 0.15, y + s * 0.85);
      ctx.lineTo(x + s * 0.85, y + s * 0.15);
      ctx.stroke();
    }
  }

  // trail
  ctx.fillStyle = "rgba(28,34,41,0.25)";
  for (const cell of scene.trail) {
    const [cx, cy] = center(l, cell);
    ctx.beginPath();
    ctx.arc(cx, cy, Math.max(1.5, s * 0.05), 0, Math.PI * 2);
    ctx.fill();
  }

  // route: thin line, slow marching dashes, arrow head
  if (scene.route.length > 1) {
    ctx.strokeStyle = COLORS.route;
    ctx.lineWidth = Math.max(2, s * 0.05);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.setLineDash([s * 0.25, s * 0.12]);
    ctx.lineDashOffset = -t * s * 0.6;
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
      ctx.moveTo(bx + Math.cos(ang) * s * 0.18, by + Math.sin(ang) * s * 0.18);
      ctx.lineTo(bx + Math.cos(ang + 2.5) * s * 0.16, by + Math.sin(ang + 2.5) * s * 0.16);
      ctx.lineTo(bx + Math.cos(ang - 2.5) * s * 0.16, by + Math.sin(ang - 2.5) * s * 0.16);
      ctx.fill();
    }
  }

  // plan waypoints: small numbered tags in the top-right corner of the cell
  for (const w of scene.waypoints) {
    const [cx, cy] = center(l, w.cell);
    const r = Math.max(7, s * 0.14);
    const x = cx + s * 0.32;
    const y = cy - s * 0.32;
    ctx.fillStyle = COLORS.route;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = COLORS.paper;
    ctx.font = font(Math.max(8, r * 1.1), 700);
    ctx.fillText(w.label, x, y + 0.5);
  }

  // people
  const pr = Math.max(8, s * 0.28);
  for (const p of state.people) {
    if (p.status === "EVACUATED" || p.status === "CARRIED") continue; // shown at the exit / on the agent
    const [cx, cy] = center(l, p.pos);
    if (p.id === scene.targetId) {
      ctx.strokeStyle = COLORS.target;
      ctx.lineWidth = 1.5;
      ctx.setLineDash([4, 3]);
      ctx.lineDashOffset = -t * 12;
      ctx.beginPath();
      ctx.arc(cx, cy, pr + Math.max(4, s * 0.1), 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash([]);
    }
    marker(ctx, cx, cy, pr, p.id, p.status);
  }
  for (const e of state.exits) {
    // evacuees line up along the bottom of their exit
    const got = state.people.filter((p) => p.status === "EVACUATED" && key(p.pos) === key(e.pos));
    const [x, y] = cellRect(e.pos, 0);
    const r = Math.max(6, s * 0.13);
    got.forEach((p, i) => {
      marker(ctx, x + r + 2 + i * (r * 2 + 2), y + s - r - 2, r, p.id, "EVACUATED");
    });
  }

  // agent (glides): ink square, white chevron for facing; carried person rides on top
  const ax = l.ox + (agent.pos[1] + 0.5) * s;
  const ay = l.oy + (agent.pos[0] + 0.5) * s;
  const half = s * 0.27;
  ctx.save();
  ctx.translate(ax, ay);
  ctx.fillStyle = COLORS.agent;
  ctx.beginPath();
  ctx.roundRect(-half, -half, half * 2, half * 2, s * 0.06);
  ctx.fill();
  ctx.rotate(agent.facing);
  ctx.fillStyle = COLORS.paper;
  ctx.beginPath();
  ctx.moveTo(half * 0.65, 0);
  ctx.lineTo(-half * 0.4, -half * 0.5);
  ctx.lineTo(-half * 0.15, 0);
  ctx.lineTo(-half * 0.4, half * 0.5);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
  if (state.agent.carrying) {
    marker(ctx, ax + half, ay - half, Math.max(6, s * 0.14), state.agent.carrying, "CARRIED");
  }

  // hover outline (builder / event pick)
  if (scene.hover) {
    ctx.strokeStyle = scene.pickMode ? COLORS.fire : COLORS.ink;
    ctx.lineWidth = 1.5;
    ctx.strokeRect(...cellRect(scene.hover, 1));
  }
}

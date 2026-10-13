/** Pure scenario-draft operations for the builder. Validation is the engine's job, not ours. */

import type { Cell, GridState, Scenario } from "../api/client";
import { same } from "./cells";

export type Tool =
  | "select"
  | "floor"
  | "rubble"
  | "wall"
  | "fire"
  | "person"
  | "exit"
  | "agent"
  | "erase";

export const TERRAIN_CHAR: Partial<Record<Tool, string>> = { floor: ".", rubble: "r", wall: "#" };
export const MIN_SIDE = 5;
export const MAX_SIDE = 30;

export const DEFAULT_PARAMS: Scenario["params"] = {
  p_spread: 0,
  weights: {
    w_r: 5,
    w_u: 3,
    w_d: 1,
    gamma: 0.1,
    urgency_cap: 5,
    urgent_threshold: 3,
    delta: 2,
  },
  cost_model: { floor: 1, rubble: 3, exit: 1, hot_extra: 4, pickup: 1, dropoff: 1 },
};

export function blankDraft(rows = 10, cols = 10): Scenario {
  return {
    name: "My scenario",
    grid_size: [rows, cols],
    terrain: Array.from({ length: rows }, () => ".".repeat(cols)),
    agent: [0, 0],
    people: [{ id: "p1", pos: [rows - 1, Math.floor(cols / 2)], risk: 2, urgency: 2 }],
    fire: [],
    exits: [{ id: "e1", pos: [rows - 1, cols - 1], available: true }],
    scripted_events: [],
    seed: 1,
    params: structuredClone(DEFAULT_PARAMS),
  };
}

function nextId(prefix: string, ids: string[]): string {
  let n = 1;
  while (ids.includes(`${prefix}${n}`)) n++;
  return `${prefix}${n}`;
}

function setChar(row: string, col: number, ch: string): string {
  return row.slice(0, col) + ch + row.slice(col + 1);
}

/** Apply a paint/erase tool at a cell. Returns the same object when nothing changed. */
export function paint(draft: Scenario, cell: Cell, tool: Tool): Scenario {
  const [r, c] = cell;
  const ch = TERRAIN_CHAR[tool];
  if (ch !== undefined) {
    if (draft.terrain[r]?.[c] === ch) return draft;
    return {
      ...draft,
      terrain: draft.terrain.map((row, i) => (i === r ? setChar(row, c, ch) : row)),
    };
  }
  switch (tool) {
    case "fire":
      return draft.fire.some((f) => same(f, cell))
        ? draft
        : { ...draft, fire: [...draft.fire, cell] };
    case "person": {
      if (draft.people.some((p) => same(p.pos, cell))) return draft;
      const id = nextId(
        "p",
        draft.people.map((p) => p.id),
      );
      return { ...draft, people: [...draft.people, { id, pos: cell, risk: 2, urgency: 2 }] };
    }
    case "exit": {
      if (draft.exits.some((e) => same(e.pos, cell))) return draft;
      const id = nextId(
        "e",
        draft.exits.map((e) => e.id),
      );
      return { ...draft, exits: [...draft.exits, { id, pos: cell, available: true }] };
    }
    case "agent":
      return same(draft.agent, cell) ? draft : { ...draft, agent: cell };
    case "erase": {
      const cleaned: Scenario = {
        ...draft,
        fire: draft.fire.filter((f) => !same(f, cell)),
        people: draft.people.filter((p) => !same(p.pos, cell)),
        exits: draft.exits.filter((e) => !same(e.pos, cell)),
      };
      return paint(cleaned, cell, "floor");
    }
    default:
      return draft;
  }
}

/** Grow or crop the grid. Things that fall outside are dropped; the agent is clamped. */
export function resize(draft: Scenario, rows: number, cols: number): Scenario {
  const inside = ([r, c]: Cell) => r < rows && c < cols;
  const terrain = Array.from({ length: rows }, (_, r) =>
    (draft.terrain[r] ?? "").slice(0, cols).padEnd(cols, "."),
  );
  return {
    ...draft,
    grid_size: [rows, cols],
    terrain,
    agent: [Math.min(draft.agent[0], rows - 1), Math.min(draft.agent[1], cols - 1)],
    people: draft.people.filter((p) => inside(p.pos)),
    fire: draft.fire.filter(inside),
    exits: draft.exits.filter((e) => inside(e.pos)),
    scripted_events: draft.scripted_events.filter((e) => {
      const pos = e.args.pos;
      return !Array.isArray(pos) || inside(pos as Cell);
    }),
  };
}

export function personAt(draft: Scenario, cell: Cell) {
  return draft.people.find((p) => same(p.pos, cell));
}

/** Parse imported JSON: accept only objects; the engine validates the rest. */
export function parseImported(text: string): Scenario {
  const raw: unknown = JSON.parse(text);
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    throw new Error("The file must contain one scenario object.");
  }
  const d = raw as Partial<Scenario>;
  const base = blankDraft();
  return {
    ...base,
    ...d,
    scripted_events: d.scripted_events ?? [],
    params: {
      p_spread: d.params?.p_spread ?? 0,
      weights: { ...DEFAULT_PARAMS.weights, ...d.params?.weights },
      cost_model: { ...DEFAULT_PARAMS.cost_model, ...d.params?.cost_model },
    },
  };
}

/** What the canvas needs to show a draft. Hot zones are derived by the engine and appear once
 * the scenario is started, so none are drawn here. */
export function draftToState(d: Scenario): GridState {
  const names: Record<string, GridState["terrain"][number][number]> = {
    ".": "floor",
    r: "rubble",
    "#": "wall",
  };
  const terrain = d.terrain.map((row) => [...row].map((ch) => names[ch] ?? "floor"));
  for (const e of d.exits) {
    const row = terrain[e.pos[0]];
    if (row && e.pos[1] < row.length) row[e.pos[1]] = "exit";
  }
  return {
    tick: 0,
    rows: d.grid_size[0],
    cols: d.grid_size[1],
    terrain,
    fire: d.fire,
    hot: [],
    agent: { pos: d.agent, carrying: null },
    people: d.people.map((p) => ({ ...p, status: "WAITING" as const })),
    exits: d.exits.map((e) => ({ ...e, available: e.available ?? true, usable: true })),
  };
}

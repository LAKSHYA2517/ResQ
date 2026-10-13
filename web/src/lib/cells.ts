import type { Cell } from "../api/client";

export const key = (c: Cell) => `${c[0]},${c[1]}`;
export const same = (a: Cell, b: Cell) => a[0] === b[0] && a[1] === b[1];

/** Logic constants name cells `c<row>_<col>` (engine: world/grid.py cell_name). */
export function cellsIn(text: string): Cell[] {
  return [...text.matchAll(/\bc(\d+)_(\d+)\b/g)].map((m) => [Number(m[1]), Number(m[2])] as Cell);
}

export const cellName = (c: Cell) => `c${c[0]}_${c[1]}`;

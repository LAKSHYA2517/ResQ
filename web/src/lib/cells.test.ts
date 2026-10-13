import { describe, expect, it } from "vitest";
import { cellName, cellsIn } from "./cells";

describe("cell names", () => {
  it("extracts every cell constant from fact text", () => {
    expect(cellsIn("Adjacent(c3_4, c10_11) & Fire(c3_4)")).toEqual([
      [3, 4],
      [10, 11],
      [3, 4],
    ]);
  });

  it("ignores things that merely look similar", () => {
    expect(cellsIn("Person(p1, c1_2x) ac3_4 Exit(e1)")).toEqual([]);
  });

  it("round-trips with the engine's naming", () => {
    expect(cellsIn(cellName([7, 12]))).toEqual([[7, 12]]);
  });
});

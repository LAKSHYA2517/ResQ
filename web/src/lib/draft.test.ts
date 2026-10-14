import { describe, expect, it } from "vitest";
import { blankDraft, paint, personAt, resize } from "./draft";

describe("paint", () => {
  it("paints terrain without touching other rows", () => {
    const d = paint(blankDraft(5, 5), [1, 2], "wall");
    expect(d.terrain[1]).toBe("..#..");
    expect(d.terrain[0]).toBe(".....");
  });

  it("returns the same object when nothing changes (no undo noise)", () => {
    const d = paint(blankDraft(5, 5), [1, 2], "wall");
    expect(paint(d, [1, 2], "wall")).toBe(d);
  });

  it("adds people and exits with fresh ids and never stacks them on one cell", () => {
    let d = blankDraft(5, 5);
    d = paint(d, [2, 2], "person");
    d = paint(d, [2, 3], "person");
    expect(d.people.map((p) => p.id)).toEqual(["p1", "p2", "p3"]);
    expect(paint(d, [2, 2], "person")).toBe(d);
    d = paint(d, [0, 4], "exit");
    expect(d.exits.map((e) => e.id)).toEqual(["e1", "e2"]);
  });

  it("reuses the lowest free id after a delete", () => {
    let d = paint(blankDraft(5, 5), [2, 2], "person");
    d = paint(d, [4, 2], "erase"); // p1 sits at the bottom-middle by default
    d = paint(d, [3, 3], "person");
    expect(d.people.map((p) => p.id)).toEqual(["p2", "p1"]);
  });

  it("moves the agent, lights fire once, and erase clears everything on the cell", () => {
    let d = paint(blankDraft(5, 5), [3, 3], "agent");
    expect(d.agent).toEqual([3, 3]);
    d = paint(paint(d, [1, 1], "fire"), [1, 1], "fire");
    expect(d.fire).toEqual([[1, 1]]);
    d = paint(d, [1, 1], "wall");
    d = paint(d, [1, 1], "erase");
    expect(d.fire).toEqual([]);
    expect(d.terrain[1]).toBe(".....");
  });

  it("finds a person at a cell", () => {
    const d = blankDraft(5, 5);
    expect(personAt(d, [4, 2])?.id).toBe("p1");
    expect(personAt(d, [0, 0])).toBeUndefined();
  });
});

describe("resize", () => {
  it("crops, pads and drops what falls outside", () => {
    let d = paint(blankDraft(8, 8), [7, 0], "fire");
    d = paint(d, [6, 6], "wall");
    const small = resize(d, 5, 5);
    expect(small.grid_size).toEqual([5, 5]);
    expect(small.terrain).toHaveLength(5);
    expect(small.terrain.every((r) => r.length === 5)).toBe(true);
    expect(small.fire).toEqual([]);
    expect(small.people).toEqual([]); // p1 was at (7, 4)
    expect(small.exits).toEqual([]);
    const big = resize(small, 6, 9);
    expect(big.terrain[5]).toBe(".".repeat(9));
  });

  it("clamps the agent", () => {
    const d = paint(blankDraft(8, 8), [7, 7], "agent");
    expect(resize(d, 5, 6).agent).toEqual([4, 5]);
  });
});

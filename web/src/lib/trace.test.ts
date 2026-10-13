import { describe, expect, it } from "vitest";
import { replanned } from "../test/helpers";
import { eventsOf, keyed, describe as say } from "./trace";

describe("trace formatting", () => {
  it("describes every kind of event the replanned snapshot contains, with its numbers", () => {
    const kinds = new Set(replanned.trace.map((e) => e.kind));
    expect(kinds).toContain("EventApplied");
    expect(kinds).toContain("PlanInvalidated");
    for (const e of replanned.trace) {
      const text = say(e);
      expect(text.length).toBeGreaterThan(5);
      expect(text).not.toContain("undefined");
      expect(text).not.toContain("[object");
    }
  });

  it("reports an A* route with the engine's measured counts", () => {
    const e = eventsOf(replanned, "RouteComputed")[0];
    expect(e).toBeDefined();
    if (!e) return;
    expect(say(e)).toContain(`${e.data.expanded} expanded`);
    expect(say(e)).toContain(`${e.data.generated} generated`);
  });

  it("gives repeated lines distinct keys", () => {
    const e = eventsOf(replanned, "RouteComputed")[0];
    if (!e) throw new Error("fixture has no RouteComputed");
    const keys = keyed([e, e, e]).map((k) => k.key);
    expect(new Set(keys).size).toBe(3);
  });
});

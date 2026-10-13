import { describe, expect, it } from "vitest";
import { STEPS } from "./demo";

describe("guided demo", () => {
  it("covers the brief's twelve steps plus the Impossible scenario", () => {
    expect(STEPS).toHaveLength(14);
    expect(STEPS[0]?.title).toBe("Load Showcase");
    expect(STEPS.at(-1)?.title).toBe("Impossible scenario");
  });

  it("never fakes a step: unbuilt steps say which phase builds them and run nothing", () => {
    const later = STEPS.filter((s) => s.later);
    expect(later.map((s) => s.title)).toEqual([
      "Bayesian sensor network",
      "Rescue-order optimizer",
    ]);
    for (const s of later) {
      expect(s.run).toBeUndefined();
      expect(s.later).toMatch(/^Phase \d/);
    }
  });

  it("every runnable step has a caption and a panel to show", () => {
    for (const s of STEPS) {
      expect(s.caption.length).toBeGreaterThan(20);
      if (!s.later && s.run) expect(s.panel).toBeDefined();
    }
  });
});

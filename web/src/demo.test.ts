import { describe, expect, it } from "vitest";
import { STEPS } from "./demo";

describe("guided demo", () => {
  it("covers the brief's twelve steps, Prove it, and the Impossible scenario", () => {
    expect(STEPS.map((s) => s.title)).toEqual([
      "Load Showcase",
      "The state is structured data",
      "Facts and rules",
      "Forward chaining",
      "Prove it",
      "Bayesian sensor network",
      "Priority scores",
      "Algorithm race",
      "Rescue-order optimizer",
      "Plan",
      "Execute",
      "Fire on the route",
      "Fact diff and the replan",
      "Adversarial fire",
      "Final outcome",
      "Agent-type benchmark",
      "Impossible scenario",
    ]);
  });

  it("never fakes a step: anything unbuilt names its phase and runs nothing", () => {
    for (const s of STEPS.filter((s) => s.later)) {
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

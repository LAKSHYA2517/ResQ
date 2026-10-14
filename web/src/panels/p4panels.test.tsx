import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useSim } from "../store/sim";
import { useUi } from "../store/ui";
import { first, mockFetch, renderWithQuery, stuck } from "../test/helpers";
import { AgentPanel } from "./AgentPanel";
import { ProveIt } from "./ProveIt";
import { SyllabusPanel } from "./SyllabusPanel";
import { UncertaintyPanel } from "./UncertaintyPanel";

const NETWORK = {
  nodes: [
    { name: "Fire", parents: [], cpt: [{ given: [], p_true: 0.4 }] },
    {
      name: "Trapped",
      parents: ["Fire"],
      cpt: [
        { given: [true], p_true: 0.8 },
        { given: [false], p_true: 0.05 },
      ],
    },
  ],
};

beforeEach(() => {
  useSim.setState({ sessionId: "s1", head: first, cache: { 0: first }, viewTick: null });
  useUi.setState({ tab: "reasoning", focus: null });
});

describe("UncertaintyPanel", () => {
  it("shows each person's sensor readings, posterior and risk exactly as the engine sent them", async () => {
    vi.stubGlobal("fetch", mockFetch({ "GET /bayes/network": NETWORK }).fn);
    renderWithQuery(<UncertaintyPanel />);
    for (const b of first.beliefs) {
      expect(screen.getByText(b.person_id)).toBeTruthy();
      expect(screen.getAllByText(`${(b.p_trapped * 100).toFixed(1)}%`).length).toBeGreaterThan(0);
    }
    const p2 = first.beliefs.find((b) => b.person_id === "p2");
    expect(p2?.risk).toBe(5);
    expect(screen.getAllByText("Smoke ✓").length).toBe(1); // only p2 is near the fire
    expect(await screen.findByRole("img", { name: "Bayesian network" })).toBeTruthy();
  });

  it("posts the edited evidence and shows the exact posterior", async () => {
    const { fn, calls } = mockFetch({
      "GET /bayes/network": NETWORK,
      "POST /bayes/infer": {
        network: NETWORK,
        query: "Trapped",
        evidence: {},
        exact: [
          { method: "enumeration", p_true: 0.35, work: 4, time_ms: 0.1 },
          { method: "elimination", p_true: 0.35, work: 6, time_ms: 0.1 },
        ],
        p_true: 0.35,
        risk: 2,
        sampled: [],
      },
    });
    vi.stubGlobal("fetch", fn);
    renderWithQuery(<UncertaintyPanel />);
    await screen.findByRole("img", { name: "Bayesian network" });
    fireEvent.click(screen.getByRole("button", { name: "Fire: unknown" }));
    fireEvent.click(screen.getByRole("button", { name: "Infer" }));
    expect(await screen.findByText("35.0%")).toBeTruthy();
    expect(screen.getByText("Risk 2/5")).toBeTruthy();
    const body = calls.at(-1)?.body as { evidence: Record<string, boolean>; query: string };
    expect(body.query).toBe("Trapped");
    expect(body.evidence.Fire).toBe(true);
    expect("Voice" in body.evidence).toBe(false); // unknown evidence is not sent
  });
});

describe("ProveIt", () => {
  it("reports a parse error from the engine instead of guessing", async () => {
    const bad = new Response(JSON.stringify({ detail: "cannot parse goal: expected ')'" }), {
      status: 422,
    });
    vi.stubGlobal("fetch", mockFetch({ "POST /kb/query": bad }).fn);
    renderWithQuery(<ProveIt />);
    fireEvent.change(screen.getByLabelText("Goal to prove"), { target: { value: "AtRisk(p2" } });
    fireEvent.click(screen.getByRole("button", { name: "Prove" }));
    expect(await screen.findByText(/cannot parse goal/)).toBeTruthy();
  });

  it("offers example goals about the current target", () => {
    vi.stubGlobal("fetch", mockFetch({}).fn);
    renderWithQuery(<ProveIt />);
    expect(screen.getByRole("button", { name: "AtRisk(p2)" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Eligible(P)" })).toBeTruthy();
  });
});

describe("AgentPanel", () => {
  it("renders PEAS and the environment rows from the API", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "GET /agent/profile": {
          agent_type: "Utility-based agent",
          peas: { Performance: ["people evacuated"], Sensors: ["smoke"] },
          environment: [{ dimension: "Static", value: "Dynamic", why: "the fire moves" }],
        },
      }).fn,
    );
    renderWithQuery(<AgentPanel />);
    expect(await screen.findByText("Utility-based agent")).toBeTruthy();
    expect(screen.getByText("Dynamic")).toBeTruthy();
    expect(screen.getByText("the fire moves")).toBeTruthy();
  });
});

describe("SyllabusPanel", () => {
  it("jumps to the feature and asks it to run", async () => {
    renderWithQuery(<SyllabusPanel />);
    const buttons = screen.getAllByRole("button", { name: "Run it" });
    expect(buttons).toHaveLength(11);
    expect(screen.getByText("document")).toBeTruthy();
    expect(screen.getByText("out of scope")).toBeTruthy();
    fireEvent.click(buttons[2] as HTMLElement); // Module 2: search
    await waitFor(() => expect(useUi.getState().tab).toBe("search"));
    expect(useUi.getState().focus).toBe("race");
  });

  it("asks for a scenario before anything can run", () => {
    useSim.setState({ sessionId: null, head: stuck });
    renderWithQuery(<SyllabusPanel />);
    expect(screen.getByText(/Start a scenario first/)).toBeTruthy();
    expect(
      (screen.getAllByRole("button", { name: "Run it" })[0] as HTMLButtonElement).disabled,
    ).toBe(true);
  });
});

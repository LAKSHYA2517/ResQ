import { screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ExplainDialog } from "../components/ExplainDialog";
import { useSim } from "../store/sim";
import { useUi } from "../store/ui";
import {
  diff,
  eventResult,
  first,
  mockFetch,
  renderWithQuery,
  replanned,
  stuck,
} from "../test/helpers";
import { PlanningPanel } from "./PlanningPanel";
import { ReasoningPanel } from "./ReasoningPanel";

function show(head: typeof first, extra: Partial<ReturnType<typeof useSim.getState>> = {}) {
  useSim.setState({
    head,
    cache: { [head.tick]: head },
    viewTick: null,
    lastEvent: null,
    ...extra,
  });
}

beforeEach(() => {
  useUi.setState({ explain: null, showState: false, overlay: null });
  vi.stubGlobal(
    "fetch",
    mockFetch({
      "GET /kb/rules": [
        { name: "hot_zone", text: "Adjacent(X, Y) & Fire(Y) -> Hot(X)", body: [], head: "Hot(X)" },
        {
          name: "at_risk",
          text: "Person(P, X) & Unsafe(X) -> AtRisk(P)",
          body: [],
          head: "AtRisk(P)",
        },
      ],
    }).fn,
  );
});

describe("PlanningPanel", () => {
  it("shows the target, the priority breakdown and the plan with step status", () => {
    show(first);
    renderWithQuery(<PlanningPanel />);
    expect(screen.getByText("Evacuated(p2)")).toBeTruthy();
    expect(screen.getByText(/p2: 5×4 \+ 3×4 − 1×13 = 19/)).toBeTruthy();
    expect(screen.getByText("Travel(c4_4, c7_8)")).toBeTruthy();
    expect(screen.getByText("Forward state-space A* expanded", { exact: false })).toBeTruthy();
  });

  it("after a fire on the route it shows the reason and the dropped plan", () => {
    show(replanned);
    renderWithQuery(<PlanningPanel />);
    expect(screen.getAllByText(/is now on fire/).length).toBeGreaterThan(0);
    expect(screen.getByText("Previous plan (dropped)")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Explain replan" })).toBeTruthy();
  });

  it("with no valid plan it lists the engine's reasons calmly and offers no explain button", () => {
    show(stuck);
    renderWithQuery(<PlanningPanel />);
    expect(screen.getByText(/No valid plan right now/)).toBeTruthy();
    for (const reason of stuck.no_plan_reasons) expect(screen.getByText(reason)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Explain this decision" })).toBeNull();
  });

  it("asks for a scenario when there is none", () => {
    useSim.setState({ head: null, cache: {}, viewTick: null });
    renderWithQuery(<PlanningPanel />);
    expect(screen.getByText(/Start a scenario/)).toBeTruthy();
  });
});

describe("ReasoningPanel", () => {
  it("lists base facts, rules with derived counts, and derived facts with provenance", async () => {
    show(first);
    renderWithQuery(<ReasoningPanel />);
    expect(screen.getByText("Person(p2, c7_8)")).toBeTruthy();
    expect(screen.getByText(/Adjacent ×\d+ \(grid geometry, not listed\)/)).toBeTruthy();
    expect(await screen.findByText(/hot_zone:/)).toBeTruthy();
    const atRisk = first.derived.find((d) => d.fact === "AtRisk(p2)");
    expect(atRisk).toBeDefined();
    expect(screen.getAllByText("AtRisk(p2)").length).toBeGreaterThan(0);
    expect(screen.getByText(/Person\(p2, c7_8\)\s+&\s+Unsafe\(c7_8\)/)).toBeTruthy();
  });

  it("after an event it shows exactly the fact diff the API returned", () => {
    show(replanned, { lastEvent: eventResult() });
    renderWithQuery(<ReasoningPanel />);
    const box = screen.getByText("Last event changed the knowledge base").closest("section");
    expect(box).toBeTruthy();
    if (!box) return;
    for (const f of diff.added) expect(within(box).getByText(`+ ${f}`)).toBeTruthy();
    expect(within(box).getByText(/Replan reason:/)).toBeTruthy();
  });

  it("the structured-state view can be opened", () => {
    show(first);
    useUi.setState({ showState: true });
    renderWithQuery(<ReasoningPanel />);
    expect(screen.getByText(/"people"/)).toBeTruthy();
  });
});

describe("ExplainDialog", () => {
  it("shows the priority scores, the provenance and the engine trace", () => {
    show(first);
    useUi.setState({ explain: "decision" });
    renderWithQuery(<ExplainDialog />);
    expect(screen.getByText("Why p2?")).toBeTruthy();
    expect(screen.getByText(/p2: 5×4 \+ 3×4 − 1×13 = 19/)).toBeTruthy();
    expect(screen.getAllByText(/Eligible\(p2\)/).length).toBeGreaterThan(0);
    expect(screen.getByText("Engine trace")).toBeTruthy();
  });

  it("explains a replan with before and after plans", () => {
    show(replanned);
    useUi.setState({ explain: "replan" });
    renderWithQuery(<ExplainDialog />);
    expect(screen.getByText("Why did the plan change?")).toBeTruthy();
    expect(screen.getByText(/before:/)).toBeTruthy();
    expect(screen.getByText(/after:/)).toBeTruthy();
  });
});

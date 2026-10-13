import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import { eventResult, FakeSocket, first, mockFetch, replanned } from "../test/helpers";
import { useSim } from "./sim";

const session = { session_id: "s1", scenario_id: "showcase", seed: 24, snapshot: first };

function reset() {
  useSim.setState({
    sessionId: null,
    scenarioId: null,
    head: null,
    cache: {},
    rev: 0,
    viewTick: null,
    running: false,
    busy: false,
    error: null,
    lastEvent: null,
    pick: null,
    highlight: [],
  });
}

beforeEach(() => {
  reset();
  FakeSocket.last = null;
  vi.stubGlobal("WebSocket", FakeSocket);
});
afterEach(() => vi.unstubAllGlobals());

describe("sim store", () => {
  it("start mirrors the engine's first snapshot and opens the stream", async () => {
    const { fn } = mockFetch({ "POST /simulation/start": session });
    vi.stubGlobal("fetch", fn);
    await useSim.getState().start("showcase");
    const s = useSim.getState();
    expect(s.sessionId).toBe("s1");
    expect(s.head).toEqual(first);
    expect(s.cache[0]).toEqual(first);
    expect(FakeSocket.last?.url).toContain("/ws/simulation/s1");
  });

  it("applies streamed snapshots and the running/finished status messages", async () => {
    vi.stubGlobal("fetch", mockFetch({ "POST /simulation/start": session }).fn);
    await useSim.getState().start("showcase");
    const ws = FakeSocket.last;
    ws?.push({ type: "status", running: true, speed: 8 });
    expect(useSim.getState()).toMatchObject({ running: true, speed: 8 });
    ws?.push({ type: "snapshot", snapshot: { ...first, tick: 1 } });
    expect(useSim.getState().head?.tick).toBe(1);
    expect(Object.keys(useSim.getState().cache)).toEqual(["0", "1"]);
    ws?.push({ type: "finished" });
    expect(useSim.getState().running).toBe(false);
  });

  it("ignores messages from a replaced session", async () => {
    vi.stubGlobal("fetch", mockFetch({ "POST /simulation/start": session }).fn);
    await useSim.getState().start("showcase");
    const old = FakeSocket.last;
    useSim.setState({ sessionId: "other" });
    old?.push({ type: "snapshot", snapshot: { ...first, tick: 9 } });
    expect(useSim.getState().head?.tick).toBe(0);
  });

  it("run and pause go over the socket", async () => {
    vi.stubGlobal("fetch", mockFetch({ "POST /simulation/start": session }).fn);
    await useSim.getState().start("showcase");
    useSim.getState().setSpeed(16);
    useSim.getState().setRunning(true);
    useSim.getState().setRunning(false);
    expect(FakeSocket.last?.sent.map((m) => JSON.parse(m))).toEqual([
      { cmd: "run", speed: 16 },
      { cmd: "pause" },
    ]);
  });

  it("inject posts the event and exposes the diff and the replan reason", async () => {
    const { fn, calls } = mockFetch({
      "POST /simulation/start": session,
      "POST /simulation/event": eventResult(),
    });
    vi.stubGlobal("fetch", fn);
    await useSim.getState().start("showcase");
    useSim.setState({ pick: "NEW_FIRE" });
    const out = await useSim.getState().inject("NEW_FIRE", { pos: [8, 7] });
    expect(calls.at(-1)?.body).toEqual({
      session_id: "s1",
      type: "NEW_FIRE",
      args: { pos: [8, 7] },
    });
    const s = useSim.getState();
    expect(out?.replan_reason).toBe(replanned.replan_reason);
    expect(s.lastEvent?.diff.added.length).toBeGreaterThan(0);
    expect(s.head).toEqual(replanned);
    expect(s.pick).toBeNull();
  });

  it("a refused event becomes a visible message, not an exception", async () => {
    const refused = new Response(
      JSON.stringify({ detail: "cannot ignite (0, 0): the agent is standing there" }),
      { status: 409 },
    );
    vi.stubGlobal(
      "fetch",
      mockFetch({ "POST /simulation/start": session, "POST /simulation/event": refused }).fn,
    );
    await useSim.getState().start("showcase");
    const out = await useSim.getState().inject("NEW_FIRE", { pos: [0, 0] });
    expect(out).toBeNull();
    expect(useSim.getState().error).toContain("agent is standing there");
    expect(useSim.getState().busy).toBe(false);
  });

  it("scrubbing uses the cache, then the replay endpoint, and live clears it", async () => {
    const { fn, calls } = mockFetch({
      "POST /simulation/start": session,
      "GET /simulation/replay/2": { ...first, tick: 2 },
    });
    vi.stubGlobal("fetch", fn);
    await useSim.getState().start("showcase");
    FakeSocket.last?.push({ type: "snapshot", snapshot: { ...first, tick: 5 } });
    await useSim.getState().scrub(0);
    expect(useSim.getState().viewTick).toBe(0);
    expect(calls.filter((c) => c.path.startsWith("/simulation/replay"))).toHaveLength(0);
    await useSim.getState().scrub(2);
    expect(calls.at(-1)?.path).toBe("/simulation/replay/2");
    expect(useSim.getState().cache[2]?.tick).toBe(2);
    await useSim.getState().scrub(5); // the live tick means "live"
    expect(useSim.getState().viewTick).toBeNull();
  });

  it("an unreachable API is reported with how to fix it", async () => {
    vi.stubGlobal("fetch", () => Promise.reject(new TypeError("Failed to fetch")));
    await useSim.getState().start("showcase");
    expect(useSim.getState().error).toMatch(/Cannot reach the engine API/);
    expect(useSim.getState().head).toBeNull();
  });

  it("startDraft registers the scenario before starting it", async () => {
    const { fn, calls } = mockFetch({
      "POST /scenario": { id: "custom-1", predefined: false, scenario: {} },
      "POST /simulation/start": session,
    });
    vi.stubGlobal("fetch", fn);
    const ok = await useSim.getState().startDraft({ name: "x" } as never);
    expect(ok).toBe(true);
    expect(calls.map((c) => c.path)).toEqual(["/scenario", "/simulation/start"]);
    expect(calls[1]?.body).toMatchObject({ scenario_id: "custom-1" });
    expect(useSim.getState().scenarioId).toBe("custom-1");
  });

  it("ApiError carries the status and body", () => {
    const e = new ApiError("nope", 409, { detail: "nope" });
    expect([e.status, e.message]).toEqual([409, "nope"]);
  });
});

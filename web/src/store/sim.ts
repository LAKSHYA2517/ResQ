import { create } from "zustand";
import {
  ApiError,
  api,
  type Cell,
  type EventResult,
  type EventTypeName,
  type Scenario,
  type Snapshot,
  WS_URL,
} from "../api/client";

/** The backend owns the simulation; this store only mirrors what the engine returned. */
interface SimStore {
  sessionId: string | null;
  scenarioId: string | null;
  head: Snapshot | null; // the live tick
  cache: Record<number, Snapshot>; // ticks seen so far (the scrubber's source)
  rev: number; // bumps on every snapshot, including same-tick updates after an event
  viewTick: number | null; // null = live
  running: boolean;
  speed: number;
  busy: boolean;
  error: string | null;
  lastEvent: EventResult | null;
  pick: EventTypeName | null; // waiting for a cell click to inject this event
  highlight: Cell[]; // cells to flash on the grid (provenance, log clicks)

  start: (scenarioId: string, seed?: number) => Promise<void>;
  startDraft: (draft: Scenario) => Promise<boolean>;
  step: () => Promise<void>;
  reset: () => Promise<void>;
  inject: (type: EventTypeName, args: Record<string, unknown>) => Promise<EventResult | null>;
  setRunning: (on: boolean) => void;
  setSpeed: (speed: number) => void;
  scrub: (tick: number | null) => Promise<void>;
  setPick: (type: EventTypeName | null) => void;
  setHighlight: (cells: Cell[]) => void;
  clearError: () => void;
}

let socket: WebSocket | null = null;

const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

export const useSim = create<SimStore>((set, get) => {
  const apply = (snapshot: Snapshot) =>
    set((s) => ({
      head: snapshot,
      cache: { ...s.cache, [snapshot.tick]: snapshot },
      rev: s.rev + 1,
      running: snapshot.finished ? false : s.running,
    }));

  const connect = (sessionId: string) => {
    socket?.close();
    const ws = new WebSocket(`${WS_URL}/ws/simulation/${sessionId}`);
    ws.onmessage = (ev) => {
      const msg = JSON.parse(String(ev.data));
      if (get().sessionId !== sessionId) return;
      if (msg.type === "snapshot") apply(msg.snapshot as Snapshot);
      else if (msg.type === "status") set({ running: msg.running, speed: msg.speed });
      else if (msg.type === "finished") set({ running: false });
      else if (msg.type === "error") set({ error: String(msg.detail) });
    };
    ws.onclose = () => {
      if (socket === ws) socket = null;
    };
    socket = ws;
  };

  const begin = (id: string, scenarioId: string, head: Snapshot) => {
    set({
      sessionId: id,
      scenarioId,
      head,
      cache: { [head.tick]: head },
      rev: 1,
      viewTick: null,
      running: false,
      error: null,
      lastEvent: null,
      pick: null,
      highlight: [],
    });
    connect(id);
  };

  /** Run an API call, record its failure as a calm message instead of throwing into the UI. */
  const guarded = async <T>(fn: () => Promise<T>): Promise<T | null> => {
    set({ busy: true });
    try {
      const out = await fn();
      set({ error: null });
      return out;
    } catch (e) {
      set({ error: message(e) });
      return null;
    } finally {
      set({ busy: false });
    }
  };

  return {
    sessionId: null,
    scenarioId: null,
    head: null,
    cache: {},
    rev: 0,
    viewTick: null,
    running: false,
    speed: 4,
    busy: false,
    error: null,
    lastEvent: null,
    pick: null,
    highlight: [],

    start: async (scenarioId, seed) => {
      const session = await guarded(() => api.start(scenarioId, seed));
      if (session) begin(session.session_id, scenarioId, session.snapshot);
    },

    startDraft: async (draft) => {
      const session = await guarded(async () => {
        const created = await api.create(draft);
        return { id: created.id, ...(await api.start(created.id)) };
      });
      if (!session) return false;
      begin(session.session_id, session.id, session.snapshot);
      return true;
    },

    step: async () => {
      const { sessionId, running } = get();
      if (!sessionId || running) return;
      const snapshot = await guarded(() => api.step(sessionId));
      if (snapshot) apply(snapshot);
    },

    reset: async () => {
      const { sessionId } = get();
      if (!sessionId) return;
      const snapshot = await guarded(() => api.reset(sessionId));
      if (!snapshot) return;
      set({ cache: {}, viewTick: null, running: false, lastEvent: null, highlight: [] });
      apply(snapshot);
    },

    inject: async (type, args) => {
      const { sessionId } = get();
      if (!sessionId) return null;
      const result = await guarded(() => api.event(sessionId, type, args));
      set({ pick: null });
      if (result) {
        apply(result.snapshot);
        set({ lastEvent: result, viewTick: null });
      }
      return result;
    },

    setRunning: (on) => {
      const { sessionId, speed } = get();
      if (!sessionId) return;
      if (on) set({ viewTick: null });
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(on ? { cmd: "run", speed } : { cmd: "pause" }));
      } else {
        void api
          .run(sessionId, on ? speed : 0)
          .then((r) => set({ running: r.running }))
          .catch((e) => set({ error: message(e) }));
      }
    },

    setSpeed: (speed) => {
      set({ speed });
      if (get().running && socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ cmd: "run", speed }));
      }
    },

    scrub: async (tick) => {
      const { sessionId, head, cache } = get();
      if (tick === null || !sessionId || !head || tick >= head.tick) {
        set({ viewTick: null });
        return;
      }
      set({ viewTick: tick });
      if (cache[tick]) return;
      const snapshot = await guarded(() => api.replay(sessionId, tick));
      if (snapshot) set((s) => ({ cache: { ...s.cache, [tick]: snapshot } }));
    },

    setPick: (pick) => set({ pick }),
    setHighlight: (highlight) => set({ highlight }),
    clearError: () => set({ error: null }),
  };
});

/** The snapshot the UI is currently showing: the scrubbed tick, or the live one. */
export function useView(): Snapshot | null {
  return useSim((s) => (s.viewTick === null ? s.head : (s.cache[s.viewTick] ?? s.head)));
}

export const isApiDown = (e: string | null) => e?.startsWith("Cannot reach") ?? false;
export { ApiError };

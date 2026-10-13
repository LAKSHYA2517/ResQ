import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type RenderResult, render } from "@testing-library/react";
import type { ReactElement } from "react";
import type { EventResult, Snapshot } from "../api/client";
import fixtures from "./fixtures.json";

/** Snapshots produced by the real engine (see the generator in the P3 notes in PLAN.md). */
export const first = fixtures.first as unknown as Snapshot;
export const replanned = fixtures.replanned as unknown as Snapshot;
export const stuck = fixtures.stuck as unknown as Snapshot;
export const diff = fixtures.diff;
export const fireCell = fixtures.fireCell as [number, number];

export function eventResult(): EventResult {
  return {
    snapshot: replanned,
    diff,
    replan_reason: replanned.replan_reason,
  } as EventResult;
}

export function renderWithQuery(ui: ReactElement): RenderResult {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

/** Minimal fetch router: maps "METHOD /path" to a JSON body. Unknown routes fail loudly. */
export function mockFetch(routes: Record<string, unknown | ((body: unknown) => unknown)>) {
  const calls: { method: string; path: string; body: unknown }[] = [];
  const fn = async (url: string | URL | Request, init?: RequestInit) => {
    const u = new URL(String(url));
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    const path = u.pathname;
    calls.push({ method, path, body });
    const hit = routes[`${method} ${path}`];
    if (hit === undefined) {
      return new Response(JSON.stringify({ detail: `no mock for ${method} ${path}` }), {
        status: 404,
      });
    }
    const out = typeof hit === "function" ? (hit as (b: unknown) => unknown)(body) : hit;
    if (out instanceof Response) return out;
    return new Response(JSON.stringify(out), { status: 200 });
  };
  return { fn, calls };
}

export class FakeSocket {
  static last: FakeSocket | null = null;
  static OPEN = 1;
  readyState = 1;
  sent: string[] = [];
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  constructor(readonly url: string) {
    FakeSocket.last = this;
  }
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    this.onclose?.();
  }
  push(msg: unknown) {
    this.onmessage?.({ data: JSON.stringify(msg) });
  }
}

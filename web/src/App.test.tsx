import { render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { App } from "./App";

afterEach(() => vi.unstubAllGlobals());

it("shows API status from /health", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ json: async () => ({ status: "ok", version: "9.9.9" }) }),
  );
  render(<App />);
  expect(await screen.findByText(/ok \(v9\.9\.9\)/)).toBeTruthy();
});

it("reports an unreachable API", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("down")));
  render(<App />);
  expect(await screen.findByText(/unreachable/)).toBeTruthy();
});

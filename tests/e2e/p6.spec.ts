/** P6: trace integrity over a whole run, the command palette and the run report. */

import { type Page, expect, test } from "@playwright/test";

type Snapshot = {
  tick: number;
  status: string;
  target: string | null;
  plan: { label: string; status: string }[];
  replan_reason: string | null;
  metrics: { moves: number; path_cost: number; plans: number; replans: number; searches: number };
  state: { people: { id: string; status: string }[] };
};

const fmt = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(1));

async function sidebar(page: Page, label: string) {
  return (await page.locator("dt", { hasText: label }).locator("xpath=following-sibling::dd").innerText()).trim();
}

/** What the screen shows for this tick must be exactly what the engine returned. */
async function expectScreenMatches(page: Page, snap: Snapshot) {
  await expect(page.getByText(`tick ${snap.tick} · ${snap.status}`)).toBeVisible();
  expect(await sidebar(page, "Moves")).toBe(String(snap.metrics.moves));
  expect(await sidebar(page, "Cost paid")).toBe(fmt(snap.metrics.path_cost));
  expect(await sidebar(page, "Plans / replans")).toBe(`${snap.metrics.plans} / ${snap.metrics.replans}`);
  expect(await sidebar(page, "A* runs")).toBe(String(snap.metrics.searches));
  const rescued = snap.state.people.filter((p) => p.status === "EVACUATED").length;
  await expect(page.getByText(`rescued ${rescued}/${snap.state.people.length}`)).toBeVisible();
  const plan = page.getByRole("tabpanel", { name: "Plan" });
  for (const step of snap.plan) {
    await expect(plan.getByText(step.label, { exact: true }).first()).toBeVisible();
  }
  if (snap.target) await expect(plan.getByText(`Evacuated(${snap.target})`)).toBeVisible();
}

test("trace integrity: every tick of the Showcase run on screen equals the engine", async ({
  page,
}) => {
  test.setTimeout(180_000);
  const started = page.waitForResponse((r) => r.url().endsWith("/simulation/start"));
  await page.goto("/");
  await expect(page.getByLabel("Name")).toHaveValue("Showcase");
  await page.getByRole("button", { name: "Validate → Start" }).click();
  const { session_id: sid, snapshot } = await (await started).json();
  await page.getByRole("tab", { name: "Plan" }).click();
  await expectScreenMatches(page, snapshot);

  // Step through the whole run, checking the screen against each engine response.
  let snap: Snapshot = snapshot;
  let injected = false;
  while (snap.status === "running" && snap.tick < 200) {
    const step = page.waitForResponse((r) => r.url().endsWith("/simulation/step"));
    await page.getByRole("button", { name: /Step/ }).click();
    snap = await (await step).json();
    if (snap.tick === 6 && !injected) {
      injected = true;
      const event = page.waitForResponse((r) => r.url().endsWith("/simulation/event"));
      await page.getByRole("button", { name: /On route/ }).click();
      snap = (await (await event).json()).snapshot;
      expect(snap.replan_reason).toMatch(/is now on fire/);
      await expect(page.getByText(snap.replan_reason ?? "", { exact: false }).first()).toBeVisible();
    }
    await expectScreenMatches(page, snap);
  }
  expect(snap.status).not.toBe("running");

  // The run rebuilt from nothing but scenario + seed + event log is the same run.
  const report = await (await page.request.get(`http://localhost:8000/simulation/report?session_id=${sid}`)).json();
  expect(report.replay_identical).toBe(true);
  expect(report.ticks).toBe(snap.tick);
  expect(report.user_events).toHaveLength(1);
  for (const t of [0, 6, Math.floor(snap.tick / 2), snap.tick]) {
    const fresh = await (
      await page.request.get(`http://localhost:8000/simulation/replay/${t}?session_id=${sid}&fresh=true`)
    ).json();
    const stored = await (
      await page.request.get(`http://localhost:8000/simulation/replay/${t}?session_id=${sid}`)
    ).json();
    expect({ ...fresh.metrics, timings_ms: {} }).toEqual({ ...stored.metrics, timings_ms: {} });
    expect(fresh.state).toEqual(stored.state);
    expect(fresh.plan).toEqual(stored.plan);
  }
});

test("command palette and report export", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText(/engine v/)).toBeVisible();
  await page.getByRole("button", { name: "Validate → Start" }).click();
  await expect(page.getByText("tick 0 ·")).toBeVisible();

  await page.keyboard.press("ControlOrMeta+k");
  const palette = page.getByRole("dialog");
  await expect(palette.getByPlaceholder("Type a command…")).toBeVisible();
  await page.keyboard.type("step one");
  const stepped = page.waitForResponse((r) => r.url().endsWith("/simulation/step"));
  await page.keyboard.press("Enter");
  await stepped;
  await expect(page.getByText("tick 1 ·")).toBeVisible();

  await page.keyboard.press("ControlOrMeta+k");
  await page.keyboard.type("triage");
  const option = page.getByRole("option", { name: /Triage Dilemma/ });
  await expect(option).toBeVisible();
  const started = page.waitForResponse((r) => r.url().endsWith("/simulation/start"));
  await page.keyboard.press("Enter");
  await started;
  await expect(page.getByText(/target p2/)).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);

  const downloads: string[] = [];
  page.on("download", (d) => downloads.push(d.suggestedFilename()));
  const report = page.waitForResponse((r) => r.url().includes("/simulation/report"));
  await page.getByRole("button", { name: "⤓ Report" }).click();
  expect((await (await report).json()).scenario.name).toBe("Triage Dilemma");
  await expect.poll(() => downloads.length).toBe(2);
  expect(downloads.sort()).toEqual([
    "resq-report-triage_dilemma-t0.html",
    "resq-report-triage_dilemma-t0.json",
  ]);
});

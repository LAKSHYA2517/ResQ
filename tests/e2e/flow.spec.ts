/** P3 acceptance: a non-developer can load a scenario, play it, inject a fire, and see the
 * replan and its reason. The numbers on screen are compared with the API's own responses. */

import { type Page, expect, test } from "@playwright/test";

type Snapshot = {
  tick: number;
  target: string | null;
  priorities: { breakdown: string }[];
  plan: { label: string }[];
  replan_reason: string | null;
};

async function startShowcase(page: Page) {
  const started = page.waitForResponse((r) => r.url().endsWith("/simulation/start"));
  await page.goto("/");
  await expect(page.getByText(/engine v/)).toBeVisible();
  await expect(page.getByLabel("Name")).toHaveValue("Showcase");
  await page.getByRole("button", { name: "Validate → Start" }).click();
  return (await (await started).json()) as { session_id: string; snapshot: Snapshot };
}

test("load, play, inject a fire, see the replan and its reason", async ({ page }) => {
  const session = await startShowcase(page);

  // What the Planning tab shows is exactly what the engine returned.
  await page.getByRole("tab", { name: "Plan" }).click();
  for (const p of session.snapshot.priorities) {
    await expect(page.getByText(p.breakdown, { exact: false }).first()).toBeVisible();
  }
  for (const s of session.snapshot.plan) {
    await expect(page.getByText(s.label, { exact: true }).first()).toBeVisible();
  }
  await expect(page.getByText(`Evacuated(${session.snapshot.target})`)).toBeVisible();

  // Play a few ticks, then pause.
  await page.getByRole("button", { name: /Start/ }).click();
  await expect(page.getByText(/tick [3-9] ·/)).toBeVisible();
  await page.getByRole("button", { name: /Pause/ }).click();
  await expect(page.getByRole("button", { name: /Resume/ })).toBeVisible();

  // Inject a fire on the route.
  const event = page.waitForResponse((r) => r.url().endsWith("/simulation/event"));
  await page.getByRole("button", { name: /Fire on route/ }).click();
  const result = (await (await event).json()) as {
    snapshot: Snapshot;
    diff: { added: string[] };
    replan_reason: string | null;
  };
  expect(result.replan_reason).toMatch(/is now on fire/);
  expect(result.diff.added.some((f) => f.startsWith("Fire("))).toBe(true);

  // The replan and its reason are visible in the plan panel and the log.
  await expect(page.getByText("Plan changed")).toBeVisible();
  await expect(page.getByText(result.replan_reason ?? "", { exact: false }).first()).toBeVisible();
  await expect(page.getByText("Previous plan (dropped)")).toBeVisible();

  // The fact diff is on the Reasoning tab.
  await page.getByRole("tab", { name: "Reasoning" }).click();
  await page.getByRole("tab", { name: "Logic" }).click();
  await expect(page.getByText("Last event changed the knowledge base")).toBeVisible();
  for (const f of result.diff.added) {
    await expect(page.getByText(`+ ${f}`, { exact: true })).toBeVisible();
  }

  // Time travel: scrub back (read-only), then return to live.
  await page.getByLabel("Timeline").fill("0");
  await expect(page.getByText("Viewing tick 0 read-only")).toBeVisible();
  await page.getByRole("button", { name: /Back to live/ }).click();
  await expect(page.getByText("LIVE")).toBeVisible();

  // Run to the end: the run finishes with a measured outcome.
  await page.getByLabel("Speed").selectOption("16");
  await page.getByRole("button", { name: /Resume/ }).click();
  await expect(page.getByText(/· (complete|stuck)/)).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(/rescued \d\/3/)).toBeVisible();
});

test("an impossible scenario is reported calmly with reasons", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText(/engine v/)).toBeVisible();
  await page.getByLabel("Predefined scenario").selectOption({ label: "Impossible" });
  await expect(page.getByLabel("Name")).toHaveValue("Impossible");
  await page.getByRole("button", { name: "Validate → Start" }).click();
  await page.getByRole("tab", { name: "Plan" }).click();
  await expect(page.getByText("No valid plan right now")).toBeVisible();
  const panel = page.getByRole("tabpanel", { name: "Plan" });
  await expect(panel.getByText(/A\* found no route/)).toBeVisible();
});

test("the builder reports a bad scenario with the offending cell before it can start", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByText(/engine v/)).toBeVisible();
  await expect(page.getByLabel("Name")).toHaveValue("Showcase");
  // Paint fire onto person p1's cell (1, 3) of the Showcase and let the engine validate.
  await page.getByRole("button", { name: /Fire/ }).first().click();
  const canvas = page.getByRole("img", { name: /Scenario builder grid/ });
  const box = await canvas.boundingBox();
  if (!box) throw new Error("no canvas");
  const cell = Math.floor(Math.min(box.width / 10, box.height / 10));
  const x0 = box.x + (box.width - cell * 10) / 2;
  const y0 = box.y + (box.height - cell * 10) / 2;
  await page.mouse.click(x0 + 3.5 * cell, y0 + 1.5 * cell);
  await expect(page.getByText(/1 problem: .*starts on a fire cell/)).toBeVisible();
  await expect(page.getByRole("listitem").filter({ hasText: "(1, 3)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Validate → Start" })).toBeDisabled();
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByText("The engine found no problems")).toBeVisible();
  await expect(page.getByRole("button", { name: "Validate → Start" })).toBeEnabled();
});

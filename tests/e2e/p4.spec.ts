/** P4 acceptance: every MUST row of the syllabus map runs from the UI, and what the UI shows is
 * what the API returned. */

import { type Page, expect, test } from "@playwright/test";

async function start(page: Page, scenario = "Showcase") {
  await page.goto("/");
  await expect(page.getByText(/engine v/)).toBeVisible();
  if (scenario !== "Showcase") {
    await page.getByLabel("Predefined scenario").selectOption({ label: scenario });
  }
  await expect(page.getByLabel("Name")).toHaveValue(scenario);
  await page.getByRole("button", { name: "Validate → Start" }).click();
  await expect(page.getByText("tick 0 ·")).toBeVisible();
}

const json = async (page: Page, path: string, act: () => Promise<void>) => {
  const wait = page.waitForResponse((r) => r.url().includes(path) && r.request().method() === "POST");
  await act();
  return (await wait).json();
};

test("Module 2: eight algorithms, the race and the heuristic lab", async ({ page }) => {
  await start(page);
  await page.getByRole("tab", { name: "Search" }).click();
  for (const label of ["DLS (depth-limited)", "IDDFS", "Weighted A*"]) {
    await page.getByLabel(label).check();
  }
  const out = await json(page, "/search/compare", () =>
    page.getByRole("button", { name: "Run comparison" }).click(),
  );
  expect(out.runs).toHaveLength(8);
  const rows = page.locator("tbody tr");
  await expect(rows).toHaveCount(8);
  for (const [i, r] of out.runs.entries()) {
    await expect(rows.nth(i).locator("td").nth(3)).toHaveText(String(r.expanded));
    await expect(rows.nth(i)).toContainText(
      !r.found ? /cutoff|no route/ : r.optimal_vs_ucs ? "optimal" : "costlier",
    );
  }
  expect(out.runs.some((r: { optimal_vs_ucs: boolean }) => !r.optimal_vs_ucs)).toBe(true);

  await page.getByRole("button", { name: "🏁 Replay race" }).click();
  await expect(page.getByRole("dialog")).toContainText("Algorithm race");
  await expect(page.getByRole("dialog").locator("canvas")).toHaveCount(8);
  await page.getByRole("button", { name: "Close" }).click();

  const lab = await json(page, "/search/heuristic-check", () =>
    page.getByRole("button", { name: "Check" }).click(),
  );
  expect(lab.admissible).toBe(false); // weighted x2 overestimates
  await expect(page.getByText(/✗ not admissible \(\d+ cells\)/)).toBeVisible();
});

test("Module 4: Prove it shows forward, backward and resolution agreeing", async ({ page }) => {
  await start(page);
  const out = await json(page, "/kb/query", async () => {
    await page.getByLabel("Goal to prove").fill("RescueNow(p2)");
    await page.getByRole("button", { name: "Prove", exact: true }).click();
  });
  expect(out.agree && out.forward.holds && out.resolution.entailed).toBe(true);
  await expect(page.getByText("all methods agree")).toBeVisible();
  await expect(page.getByText(/2 · Backward chaining \(1 proof/)).toBeVisible();
  await expect(page.getByText("Empty clause □ reached", { exact: false })).toBeVisible();
  await expect(page.getByText("¬RescueNow(p2)", { exact: true })).toBeVisible();

  await page.getByLabel("Goal to prove").fill("AtRisk(p1)");
  await page.getByRole("button", { name: "Prove", exact: true }).click();
  await expect(page.getByText("✗ does not hold")).toBeVisible();
  await expect(page.getByText(/No refutation after \d+ resolvents/)).toBeVisible();

  await page.getByLabel("Goal to prove").fill("AtRisk(p2");
  await page.getByRole("button", { name: "Prove", exact: true }).click();
  await expect(page.getByText(/cannot parse goal/)).toBeVisible();
});

test("Module 5: beliefs set the risk, and sampling converges to the exact answer", async ({
  page,
}) => {
  await start(page);
  await page.getByRole("tab", { name: "Bayes" }).click();
  await expect(page.getByText(/Risk 5\/5/)).toBeVisible(); // p2 next to the fire
  const out = await json(page, "/bayes/infer", () =>
    page.getByRole("button", { name: "Infer" }).click(),
  );
  await expect(page.getByText(`${(out.p_true * 100).toFixed(1)}%`).first()).toBeVisible();
  expect(Math.abs(out.exact[0].p_true - out.exact[1].p_true)).toBeLessThan(1e-9);
  for (const s of out.sampled) expect(s.error).toBeLessThan(0.05);
  await expect(page.getByRole("img", { name: /estimate − exact/ })).toBeVisible();
});

test("Module 3: order optimizer against the optimum, and alpha-beta savings", async ({ page }) => {
  await start(page, "Mass Evacuation");
  await page.getByRole("tab", { name: "Optimize" }).click();
  const order = await json(page, "/optimize/order", () =>
    page.getByRole("button", { name: "Optimise" }).click(),
  );
  expect(order.people).toHaveLength(7);
  const greedy = order.rows.find((r: { method: string }) => r.method === "greedy");
  expect(greedy.gap).toBeGreaterThan(0);
  await expect(page.getByText("Exhaustive optimum")).toBeVisible();
  await expect(page.getByRole("img", { name: /best cost so far/ })).toBeVisible();

  const game = await json(page, "/adversarial/move", () =>
    page.getByRole("button", { name: "Analyse this move" }).click(),
  );
  expect(game.same_move && game.same_value).toBe(true);
  expect(game.alphabeta.nodes).toBeLessThan(game.minimax.nodes);
  await expect(page.getByText("✓ same move and value")).toBeVisible();
  await expect(page.getByText(new RegExp(`${game.nodes_saved} nodes saved`))).toBeVisible();

  await page.getByRole("button", { name: "Restart with worst-case fire" }).click();
  await expect(page.getByText("worst-case fire", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Agent" }).click();
  await expect(page.getByText("Multi-agent (competitive)")).toBeVisible();
});

test("Modules 6 and 1: planners agree, PEAS, and the syllabus Run it links", async ({ page }) => {
  await start(page);
  await page.getByRole("tab", { name: "Plan" }).click();
  const plans = await json(page, "/plan/compare", () =>
    page.getByRole("button", { name: "Compare planners" }).click(),
  );
  expect(plans.equal_cost).toBe(true);
  expect(plans.rows).toHaveLength(4);
  await expect(page.getByText("✓ all planners found the same cost")).toBeVisible();

  await page.getByRole("tab", { name: "Agent" }).click();
  await expect(page.getByText("Performance")).toBeVisible();
  await expect(page.getByText("Stochastic", { exact: true })).toBeVisible();

  await page.getByRole("tab", { name: "Syllabus" }).click();
  await expect(page.getByRole("button", { name: "Run it" })).toHaveCount(9);
  const proved = page.waitForResponse((r) => r.url().includes("/kb/query"));
  await page.getByRole("button", { name: "Run it" }).nth(5).click(); // backward chaining row
  await proved;
  await expect(page.getByRole("tab", { name: "Logic" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByText("all methods agree")).toBeVisible();
});

test("the guided demo runs start to finish with no errors", async ({ page }) => {
  test.setTimeout(240_000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await page.goto("/");
  await expect(page.getByText(/engine v/)).toBeVisible();
  await page.getByRole("button", { name: "Guided demo" }).click();
  const bar = page.locator('section[aria-label="Guided demo"]');
  const titles: string[] = [];
  for (let i = 0; i < 16; i++) {
    await expect(bar.getByText(`step ${i + 1} of 16`)).toBeVisible({ timeout: 120_000 });
    await expect(bar.getByRole("button", { name: "Working…" })).toHaveCount(0, { timeout: 120_000 });
    titles.push(await bar.locator(".font-semibold").first().innerText());
    await expect(bar).not.toContainText("Not built yet");
    if (titles[i] === "Algorithm race") {
      // the race opens as a modal: watch it, then close it to carry on
      await expect(page.getByRole("dialog")).toContainText("Algorithm race");
      await page.getByRole("button", { name: "Close" }).click();
    }
    if (i < 15) await bar.getByRole("button", { name: "Next →" }).click();
  }
  expect(titles[0]).toBe("Load Showcase");
  expect(titles[15]).toBe("Impossible scenario");
  await expect(page.getByText("No valid plan right now")).toBeVisible();
  expect(errors).toEqual([]);
});

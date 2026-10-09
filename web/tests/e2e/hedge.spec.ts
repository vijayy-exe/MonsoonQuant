import { expect, test } from "@playwright/test";

// SPEC §11 E2E: "Hedge Lab produces a result" -- runs the real optimiser
// against the live API, not a mock.
test("hedge lab runs the optimiser and shows a result", async ({ page }) => {
  // The underlying official-index reconstruction this hits is cached by
  // request hash, but a cold cache (e.g. right after restarting uvicorn)
  // genuinely costs ~8s per src/mq/api/routes/risk.py's own docstring --
  // give it real room rather than a tight timeout that flakes on a cold run.
  test.setTimeout(60_000);
  await page.goto("/hedge");

  await expect(page.getByRole("heading", { name: "Hedge Lab" })).toBeVisible();
  await page.getByRole("button", { name: "Run optimiser" }).click();

  await expect(page.getByRole("heading", { name: "Min-variance" })).toBeVisible({
    timeout: 45_000,
  });
  await expect(page.getByRole("heading", { name: "CVaR95" })).toBeVisible();
  await expect(page.getByText("hedge effectiveness")).toBeVisible();
});

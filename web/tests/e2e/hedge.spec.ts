import { expect, test } from "@playwright/test";

// SPEC §11 E2E: "Hedge Lab produces a result" -- runs the real optimiser
// against the live API, not a mock.
test("hedge lab runs the optimiser and shows a result", async ({ page }) => {
  test.setTimeout(30_000);
  await page.goto("/hedge");

  await expect(page.getByRole("heading", { name: "Hedge Lab" })).toBeVisible();
  await page.getByRole("button", { name: "Run optimiser" }).click();

  await expect(page.getByRole("heading", { name: "Min-variance" })).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByRole("heading", { name: "CVaR95" })).toBeVisible();
  await expect(page.getByText("hedge effectiveness")).toBeVisible();
});

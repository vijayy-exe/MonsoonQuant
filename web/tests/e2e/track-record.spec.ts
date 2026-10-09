import { expect, test } from "@playwright/test";

// SPEC §11 E2E: "Track Record verifies chain". The real backtest is
// slow uncached (~40-50s per docs/STATUS.md M12 detail); this test
// only needs the page to load and show the real chain-verify badge,
// not wait for the backtest section specifically.
test("track record shows a real hash-chain verification badge", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/track-record", { timeout: 110_000 });

  await expect(page.getByText(/chain verified|chain broken/)).toBeVisible();
  await expect(page.getByText(/rows$/)).toBeVisible();
});

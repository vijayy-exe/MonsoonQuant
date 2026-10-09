import { expect, test } from "@playwright/test";

// SPEC §11 E2E: "Overview loads". Hedge Lab / Track Record smoke tests
// are added once those pages exist (M13 in progress -- see docs/STATUS.md).
test("overview loads real contract cards from the live API", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await expect(page.getByText("RAINCHNNAI-OCT26")).toBeVisible();
  await expect(page.getByText("model fair value").first()).toBeVisible();
  await expect(page.getByText("index values").first()).toBeVisible();
});

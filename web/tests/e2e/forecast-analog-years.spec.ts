import { expect, test } from "@playwright/test";

// SPEC §10 page 3's "analog-years table" -- a real, live on-demand
// re-run of analog_v1's own selection step (M7's own stated gap, now
// closed). First load is genuinely slow uncached (~15-20s), so this
// needs real room. Whether the table renders real years or the honest
// "unavailable" state depends on whether real-time IMD/ONI/DMI data
// actually covers *today* (it may lag by design -- confirmed directly
// while building this) -- both are correct outcomes; a crash isn't.
test("forecast page's analog-years section resolves to a real table or an honest empty state", async ({
  page,
}) => {
  test.setTimeout(60_000);
  await page.goto("/series/RAINCHNNAI-OCT26/forecast?model=analog_v1", { timeout: 50_000 });

  await expect(page.getByRole("heading", { name: "RAINCHNNAI-OCT26" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Analog years" })).toBeVisible();

  const table = page.getByRole("table").last();
  const unavailable = page.getByText("Analog selection unavailable");
  await expect(table.or(unavailable)).toBeVisible({ timeout: 40_000 });
});

import { expect, test } from "@playwright/test";

// SPEC §10 page 6: "MapLibre grid heatmap". Confirms the real map
// actually renders (a WebGL canvas painted by maplibre-gl, not a
// placeholder) against the live /basis endpoint -- first load is
// genuinely slow uncached (~48s, see docs/STATUS.md's M10/M12 detail),
// so this needs real room.
test("basis map renders a real MapLibre canvas over live per-cell data", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/basis", { timeout: 110_000 });

  await expect(page.getByRole("heading", { name: "Basis Map" })).toBeVisible();
  const canvas = page.locator("canvas.maplibregl-canvas");
  await expect(canvas).toBeVisible({ timeout: 90_000 });

  // The canvas should have actually painted something (a non-zero
  // size), not just exist as an empty DOM node.
  const box = await canvas.boundingBox();
  expect(box?.width).toBeGreaterThan(0);
  expect(box?.height).toBeGreaterThan(0);
});

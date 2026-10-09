import { existsSync, readdirSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { defineConfig } from "@playwright/test";

/**
 * This sandbox's network blocks cdn.playwright.dev, so the
 * `chromium-headless-shell` binary Playwright wants for headless runs
 * can never download -- only full "chromium" (a regular Chrome-for-
 * Testing build) does, via a different path. Point headless runs at
 * that full browser instead, when present; untouched (normal resolution)
 * wherever both binaries install fine, e.g. CI. Not re-debugged next
 * time -- see docs/DECISIONS.md.
 */
function findFullChromiumExecutable(): string | undefined {
  const cacheDir = join(homedir(), "Library", "Caches", "ms-playwright");
  if (!existsSync(cacheDir)) return undefined;
  const dir = readdirSync(cacheDir).find((d) => /^chromium-\d+$/.test(d));
  if (!dir) return undefined;
  const candidate = join(
    cacheDir,
    dir,
    "chrome-mac-arm64",
    "Google Chrome for Testing.app",
    "Contents",
    "MacOS",
    "Google Chrome for Testing",
  );
  return existsSync(candidate) ? candidate : undefined;
}

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  use: {
    baseURL: process.env.MQ_WEB_BASE_URL ?? "http://localhost:3000",
    launchOptions: {
      executablePath: findFullChromiumExecutable(),
    },
  },
});

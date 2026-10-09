"use client";

import { useSyncExternalStore } from "react";

type Theme = "light" | "dark";

const CHANGE_EVENT = "mq-theme-change";

function readStoredTheme(): Theme | null {
  try {
    const stored = localStorage.getItem("mq-theme");
    return stored === "light" || stored === "dark" ? stored : null;
  } catch {
    return null;
  }
}

function getSnapshot(): Theme {
  return (
    readStoredTheme() ??
    (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")
  );
}

// Matches the server's default so the pre-hydration DOM (painted by the
// blocking <head> script in layout.tsx) never disagrees with React.
function getServerSnapshot(): Theme {
  return "light";
}

function subscribe(onChange: () => void) {
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  window.addEventListener(CHANGE_EVENT, onChange);
  media.addEventListener("change", onChange);
  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange);
    media.removeEventListener("change", onChange);
  };
}

function setTheme(theme: Theme) {
  try {
    localStorage.setItem("mq-theme", theme);
  } catch {
    // localStorage unavailable (private mode, etc.) -- theme just won't persist
  }
  document.documentElement.setAttribute("data-theme", theme);
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

export function ThemeToggle() {
  const theme = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  return (
    <button
      type="button"
      onClick={() => setTheme(theme === "light" ? "dark" : "light")}
      className="rounded-md border border-border px-3 py-1 text-xs text-muted transition hover:text-foreground"
      aria-label="Toggle light/dark theme"
    >
      {theme === "light" ? "dark" : "light"} mode
    </button>
  );
}

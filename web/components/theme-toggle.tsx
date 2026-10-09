"use client";

import { useEffect, useState } from "react";

type Theme = "light" | "dark";

function applyTheme(theme: Theme) {
  document.documentElement.setAttribute("data-theme", theme);
  try {
    localStorage.setItem("mq-theme", theme);
  } catch {
    // localStorage unavailable (private mode, etc.) -- theme just won't persist
  }
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme | null>(null);

  useEffect(() => {
    const stored = (() => {
      try {
        return localStorage.getItem("mq-theme") as Theme | null;
      } catch {
        return null;
      }
    })();
    setTheme(
      stored ?? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"),
    );
  }, []);

  if (theme === null) return <span className="inline-block h-8 w-16" aria-hidden />;

  return (
    <button
      type="button"
      onClick={() => {
        const next: Theme = theme === "light" ? "dark" : "light";
        setTheme(next);
        applyTheme(next);
      }}
      className="rounded-md border border-border px-3 py-1 text-xs text-muted transition hover:text-foreground"
      aria-label="Toggle light/dark theme"
    >
      {theme === "light" ? "dark" : "light"} mode
    </button>
  );
}

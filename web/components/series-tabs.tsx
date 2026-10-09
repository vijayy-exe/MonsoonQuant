import Link from "next/link";

const TABS = [
  { href: "pricing", label: "Pricing" },
  { href: "forecast", label: "Forecast" },
  { href: "risk", label: "Risk" },
];

export function SeriesTabs({ seriesId, active }: { seriesId: string; active: string }) {
  return (
    <nav className="flex gap-4 border-b border-border text-sm">
      {TABS.map((t) => (
        <Link
          key={t.href}
          href={`/series/${seriesId}/${t.href}`}
          className={`-mb-px border-b-2 px-1 py-2 ${
            t.href === active
              ? "border-accent text-foreground"
              : "border-transparent text-muted hover:text-foreground"
          }`}
        >
          {t.label}
        </Link>
      ))}
    </nav>
  );
}

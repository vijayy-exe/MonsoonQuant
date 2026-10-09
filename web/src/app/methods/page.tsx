import { readFile } from "node:fs/promises";
import path from "node:path";
import { marked } from "marked";
import Link from "next/link";

export const instant = false;

const DOCS = [
  "api",
  "basis",
  "burn_distribution",
  "conditioned",
  "forecasting",
  "greeks",
  "hedge",
  "mpr",
  "parametric",
  "scenarios",
] as const;

const METHODS_DIR = path.join(process.cwd(), "..", "docs", "methods");

export default async function MethodsPage({
  searchParams,
}: {
  searchParams: Promise<{ doc?: string }>;
}) {
  const { doc } = await searchParams;
  const active = DOCS.includes(doc as (typeof DOCS)[number]) ? (doc as (typeof DOCS)[number]) : DOCS[0];

  const raw = await readFile(path.join(METHODS_DIR, `${active}.md`), "utf-8").catch(
    () => "_Could not read this methods note._",
  );
  const html = await marked.parse(raw);

  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <h1 className="text-lg font-semibold">Methods</h1>
      <p className="mt-1 text-sm text-muted">
        Rendered straight from `docs/methods/*.md` in the repo — the same
        notes written while each milestone was built, not a separate
        marketing summary.
      </p>

      <div className="mt-6 grid grid-cols-1 gap-8 md:grid-cols-[180px_1fr]">
        <nav className="flex flex-row flex-wrap gap-2 md:flex-col">
          {DOCS.map((d) => (
            <Link
              key={d}
              href={`/methods?doc=${d}`}
              className={`rounded-md px-2 py-1 text-xs ${
                d === active
                  ? "bg-accent text-accent-foreground"
                  : "text-muted hover:text-foreground"
              }`}
            >
              {d.replace(/_/g, " ")}
            </Link>
          ))}
        </nav>

        {/* Trusted repo-local markdown (docs/methods/*.md), not user input. */}
        <article className="prose-mq" dangerouslySetInnerHTML={{ __html: html }} />
      </div>

      <section className="mt-12 border-t border-border pt-6">
        <h2 className="text-sm font-semibold text-foreground">Data sources &amp; licences</h2>
        <p className="mt-1 text-sm text-muted">
          Full citations and VERIFY status (V1–V12) for every official
          document used (NCDEX contract specs, IMD rainfall, ONI/DMI) are
          in <code>docs/VERIFY.md</code> in the repo — V1-V11 are closed;
          V12 (data-redistribution licensing) stays open, no sourced
          document states explicit terms.
        </p>
      </section>

      <section className="mt-6">
        <h2 className="text-sm font-semibold text-foreground">Changelog</h2>
        <p className="mt-1 text-sm text-muted">
          <code>docs/PROGRESS.md</code> in the repo is the running,
          newest-first log every milestone was built against — not
          reproduced here since it&apos;s a multi-thousand-line file, not a
          dashboard-sized summary.
        </p>
      </section>
    </div>
  );
}

/** SPEC §10: "empty/stale states designed explicitly" -- never a blank div. */
export function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="rounded-lg border border-dashed border-border p-6 text-sm">
      <p className="font-medium text-foreground">{title}</p>
      <p className="mt-1 text-muted">{detail}</p>
    </div>
  );
}

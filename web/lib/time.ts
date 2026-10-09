/**
 * One layer of indirection around `Date.now()` so UI-only "where are we
 * in this known date range" math (season progress bars, freshness
 * staleness) doesn't read as a component rendering an impure value --
 * the underlying number still comes fresh from the server clock on
 * every request (this route opts out of static prerendering).
 */
export function nowMs(): number {
  return Date.now();
}

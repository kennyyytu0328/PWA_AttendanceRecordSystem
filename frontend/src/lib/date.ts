/**
 * Date helpers that stay correct in a UTC+8 (Asia/Taipei) browser.
 *
 * Attendance timestamps are serialized by the backend as *naive* local (Taiwan)
 * datetimes with no timezone suffix, e.g. "2026-07-01T07:41:00". Passing such a
 * string through `new Date(iso).toISOString()` reinterprets it in the browser's
 * local zone and then converts to UTC — which rolls the calendar date back a day
 * for any punch before 08:00 local (08:00 Taipei == 00:00 UTC). That silently
 * breaks date-keyed lookups (e.g. the team page status badge) and date grouping.
 *
 * These helpers derive the calendar date without any UTC round-trip.
 */

/** Literal `YYYY-MM-DD` from a naive ISO timestamp — no timezone shift. */
export function isoDateOnly(iso: string): string {
  return iso.split("T")[0];
}

/** `YYYY-MM-DD` from a Date's *local* calendar components. */
export function localDateString(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** Today's date as `YYYY-MM-DD` in the browser's local zone. */
export function localToday(): string {
  return localDateString(new Date());
}

import type { DayKind, WorkdayInfo } from "@/types";

/** Weekday-only fallback. Used when no WorkdayInfo is available. */
export function deriveDayKindFromDate(date: Date): DayKind {
  const wd = date.getDay(); // 0 = Sunday, 6 = Saturday
  if (wd === 0) return "REGULAR_LEAVE";
  if (wd === 6) return "REST_DAY";
  return "WORKDAY";
}

/**
 * Derive DayKind from a WorkdayInfo, with a weekday fallback when the
 * backend didn't supply `day_kind`. Mirrors backend `classify_day_kind`.
 */
export function deriveDayKindFromWorkday(d: WorkdayInfo): DayKind {
  if (d.day_kind) return d.day_kind;
  const wd = new Date(d.date).getDay();
  if (wd === 0) return "REGULAR_LEAVE";
  if (d.is_makeup_workday) return "MAKEUP_WORKDAY";
  if (wd === 6 && d.is_holiday) return "REST_DAY";
  if (d.is_holiday) return "NATIONAL_HOLIDAY";
  return "WORKDAY";
}

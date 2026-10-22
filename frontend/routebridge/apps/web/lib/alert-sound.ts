/** The bell's notifications as counts per kind ("unassigned": 3). The Admin hears an alert when any count goes up. */
export type AlertCounts = Record<string, number>;

/** True when a notification is new or has more items than before. The first look (prev = null) stays quiet. */
export function alertsGrew(prev: AlertCounts | null, now: AlertCounts): boolean {
  if (prev === null) return false;
  return Object.entries(now).some(([key, count]) => count > (prev[key] ?? 0));
}

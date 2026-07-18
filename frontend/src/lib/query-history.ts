// Recent-stock-query quick-pick list — plain localStorage, no backend table. This is a
// per-device "what did I just look at" convenience, not data that needs to survive a browser
// wipe or sync across devices, so a DB table would be infrastructure ahead of actual need.

export type RecentQuery = { symbol: string; name: string };

const STORAGE_KEY = "stock-recent-queries";
const MAX_ENTRIES = 10;

export function getRecentQueries(): RecentQuery[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function pushRecentQuery(entry: RecentQuery): void {
  if (typeof window === "undefined") return;
  const existing = getRecentQueries().filter((e) => e.symbol !== entry.symbol);
  const updated = [entry, ...existing].slice(0, MAX_ENTRIES);
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
  } catch {
    // localStorage unavailable (private browsing quota etc.) — history just won't persist
  }
}

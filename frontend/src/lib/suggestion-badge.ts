// Shared 4-tier suggestion badge — first established in overnight-sentiment-panel.tsx, now also
// used by portfolio-dashboard.tsx. Same red=bullish/emerald=bearish/amber=neutral convention as
// the rest of this app (NOT a red=bad/green=good traffic light).
export type Suggestion = "add" | "hold" | "watch" | "trim";

export const SUGGESTION_BADGE: Record<Suggestion, string> = {
  add: "bg-red-600 text-white",
  hold: "bg-amber-500 text-white",
  watch: "bg-amber-400 text-white",
  trim: "bg-emerald-600 text-white",
};

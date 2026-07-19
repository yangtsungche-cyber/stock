import { useMemo, useState } from "react";

export type SortDirection = "asc" | "desc";

/**
 * Generic click-to-sort helper for table rows. `getValue` extracts the comparable value for a
 * given column key from a row — kept as a caller-supplied function (not direct property access)
 * since some columns sort by a computed/derived value (e.g. market value = shares * price) rather
 * than a raw field.
 */
export function useSortableData<T>(
  rows: T[],
  getValue: (row: T, key: string) => string | number | null | undefined,
  initial?: { key: string; dir: SortDirection }
) {
  const [sortKey, setSortKey] = useState<string | null>(initial?.key ?? null);
  const [sortDir, setSortDir] = useState<SortDirection>(initial?.dir ?? "desc");

  function requestSort(key: string) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  const sortedRows = useMemo(() => {
    if (!sortKey) return rows;
    const withValues = rows.map((row) => ({ row, value: getValue(row, sortKey) }));
    withValues.sort((a, b) => {
      const av = a.value;
      const bv = b.value;
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      let cmp: number;
      if (typeof av === "string" || typeof bv === "string") {
        cmp = String(av).localeCompare(String(bv), "zh-Hant");
      } else {
        cmp = av - bv;
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
    return withValues.map((w) => w.row);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, sortKey, sortDir]);

  return { sortedRows, sortKey, sortDir, requestSort };
}

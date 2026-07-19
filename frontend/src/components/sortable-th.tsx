import type { ReactNode } from "react";
import type { SortDirection } from "@/lib/use-sortable-data";

export function SortableTh({
  sortKey,
  label,
  activeKey,
  dir,
  onSort,
  align = "right",
  className = "",
}: {
  sortKey: string;
  label: ReactNode;
  activeKey: string | null;
  dir: SortDirection;
  onSort: (key: string) => void;
  align?: "left" | "right" | "center";
  className?: string;
}) {
  const active = activeKey === sortKey;
  const alignClass = align === "right" ? "text-right" : align === "center" ? "text-center" : "text-left";
  return (
    <th
      className={`py-1 pr-2 cursor-pointer select-none hover:text-foreground ${alignClass} ${className}`}
      onClick={() => onSort(sortKey)}
    >
      {label}
      <span className="ml-0.5 inline-block w-3 text-center">{active ? (dir === "asc" ? "▲" : "▼") : ""}</span>
    </th>
  );
}

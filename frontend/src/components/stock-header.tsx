import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import type { MockStock } from "@/lib/mock-stock";

export function StockHeader({
  stock,
  quoteUnavailable,
}: {
  stock: MockStock;
  quoteUnavailable?: boolean;
}) {
  const isUp = stock.change > 0;
  const isDown = stock.change < 0;

  return (
    <div className="flex flex-wrap items-end justify-between gap-4 border-b pb-4">
      <div>
        <Link href="/" className="text-sm text-muted-foreground hover:underline">
          ← 重新搜尋
        </Link>
        <div className="mt-1 flex items-baseline gap-2">
          <h1 className="text-2xl font-semibold">{stock.symbol}</h1>
          <span className="text-lg text-muted-foreground">{stock.name}</span>
          <Badge variant="secondary">{stock.market}</Badge>
        </div>
      </div>

      <div className="text-right">
        {quoteUnavailable ? (
          <div className="text-sm text-muted-foreground">無法取得即時報價</div>
        ) : (
          <>
            <div className="text-2xl font-semibold">{stock.price.toFixed(2)}</div>
            <div
              className={
                isUp
                  ? "text-red-500"
                  : isDown
                    ? "text-emerald-500"
                    : "text-muted-foreground"
              }
            >
              {isUp ? "+" : ""}
              {stock.change.toFixed(2)} ({isUp ? "+" : ""}
              {stock.changePercent.toFixed(2)}%)
            </div>
          </>
        )}
      </div>
    </div>
  );
}

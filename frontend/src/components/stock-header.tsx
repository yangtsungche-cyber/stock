import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { MockStock } from "@/lib/mock-stock";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const MARKET_LABEL: Record<MockStock["market"], string> = {
  TWSE: "上市",
  TPEx: "上櫃",
  興櫃: "興櫃",
};

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
          <Badge variant="secondary">{MARKET_LABEL[stock.market]}</Badge>
        </div>
      </div>

      <div className="flex flex-col items-end gap-2 text-right">
        <a href={`${API_URL}/api/v1/stocks/${encodeURIComponent(stock.symbol)}/report.pdf`}>
          <Button variant="outline" size="sm">
            下載 PDF 報告
          </Button>
        </a>
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

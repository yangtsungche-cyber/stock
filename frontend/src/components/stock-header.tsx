"use client";

import { useState } from "react";
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
  const [downloading, setDownloading] = useState(false);
  const isUp = stock.change > 0;
  const isDown = stock.change < 0;

  async function downloadReport() {
    // 用 fetch 而非 <a href> 直接連到後端——後端現在要求 X-API-Key，plain 的瀏覽器
    // 導覽沒辦法帶自訂 header，只有 fetch（會被 api-key-fetch-patch.tsx 自動加上
    // 這把 key）才能通過閘門，所以下載一律先 fetch 回 blob 再觸發存檔。
    setDownloading(true);
    try {
      const res = await fetch(
        `${API_URL}/api/v1/stocks/${encodeURIComponent(stock.symbol)}/report.pdf`,
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${stock.symbol}_分析報告.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setDownloading(false);
    }
  }

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
        <Button variant="outline" size="sm" onClick={downloadReport} disabled={downloading}>
          {downloading ? "下載中…" : "下載 PDF 報告"}
        </Button>
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

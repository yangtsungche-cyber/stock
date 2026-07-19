"use client";

import { Info } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { SortableTh } from "@/components/sortable-th";
import { useSortableData } from "@/lib/use-sortable-data";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type QualityStockRow = {
  rank: number;
  symbol: string;
  name: string;
  market: string;
  price: number | null;
  fcf_return_latest_pct: number;
  fcf_return_3y_avg_pct: number;
  pb_ratio: number;
  pb_rank: number;
  pe_ratio: number;
  pe_rank: number;
  dividend_yield_pct: number;
  yield_rank: number;
  combined_score: number;
};

type QualityStocksResponse = {
  screened_at: string | null;
  stocks: QualityStockRow[];
};

// Same red=bullish/emerald=bearish convention as the rest of this app — here
// applied to FCF return (positive = red, growing capital-efficiency).
function FcfCell({ pct }: { pct: number }) {
  const color = pct > 0 ? "text-red-600" : pct < 0 ? "text-emerald-600" : "text-muted-foreground";
  return (
    <span className={`tabular-nums font-medium ${color}`}>
      {pct > 0 ? "+" : ""}
      {pct.toFixed(2)}%
    </span>
  );
}

function CombinedScoreExplainer() {
  return (
    <Dialog>
      <DialogTrigger
        render={<Button variant="ghost" size="icon-sm" className="ml-1 align-middle" />}
      >
        <Info className="size-3.5 text-muted-foreground" />
        <span className="sr-only">綜合分數說明</span>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>綜合分數是什麼？</DialogTitle>
        </DialogHeader>
        <div className="space-y-2 text-sm text-muted-foreground">
          <p>
            綜合分數 = 股價淨值比排名 + 本益比排名 + 股息殖利率排名（三項排名都只在「已經通過
            自由現金流報酬率品質篩選」的候選股裡面比較，數字越小代表越好：股價淨值比/本益比排名
            #1 = 最便宜、殖利率排名 #1 = 殖利率最高）。
          </p>
          <p className="font-medium text-foreground">
            綜合分數越低，代表這檔股票同時具備「相對便宜」與「相對高殖利率」——也就是在體質已經
            及格的這群股票裡，目前價格相對划算的程度。分數本身不代表獲利能力強弱，那已經由
            「3年FCF報酬率均值」篩選過了；綜合分數只反映「現在買貴不貴」。
          </p>
          <p>排名由小到大排序，所以清單最上面就是目前相對最划算的標的。</p>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function getSortValue(row: QualityStockRow, key: string): string | number | null {
  switch (key) {
    case "name":
      return `${row.symbol} ${row.name}`;
    case "price":
      return row.price;
    case "fcf_return":
      return row.fcf_return_3y_avg_pct;
    case "pb":
      return row.pb_ratio;
    case "pe":
      return row.pe_ratio;
    case "yield":
      return row.dividend_yield_pct;
    case "combined_score":
      return row.combined_score;
    default:
      return row.rank;
  }
}

export function QualityStocksList() {
  const [status, setStatus] = useState<"loading" | "done" | "error">("loading");
  const [data, setData] = useState<QualityStocksResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchList() {
      setStatus("loading");
      setError(null);
      try {
        const res = await fetch(`${API_URL}/api/v1/quality-stocks`);
        if (!res.ok) {
          const body = await res.json().catch(() => null);
          throw new Error(body?.detail ?? `HTTP ${res.status}`);
        }
        const body: QualityStocksResponse = await res.json();
        setData(body);
        setStatus("done");
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        setStatus("error");
      }
    }
    fetchList();
  }, []);

  const stocks = data?.stocks ?? [];
  const { sortedRows, sortKey, sortDir, requestSort } = useSortableData(stocks, getSortValue, {
    key: "rank",
    dir: "asc",
  });

  return (
    <Card className="w-full max-w-4xl">
      <CardHeader>
        <CardTitle className="text-base">財報狗績優股清單</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          全市場批次篩選：排除自由現金流報酬率較前一年度下滑的公司，取 3 年平均自由現金流報酬率前 20%
          中，再依股價淨值比／本益比／股息殖利率的綜合排名，找出相對低估的績優股（前 80 名）。全市場批次需數小時，
          由後台排程/手動執行 `screen_quality_stocks.py` 產生，此處僅顯示最新一次結果快照。
        </p>

        {status === "loading" && <p className="text-sm text-muted-foreground">讀取中…</p>}
        {status === "error" && <p className="text-sm text-muted-foreground">讀取失敗：{error}</p>}

        {status === "done" && stocks.length === 0 && (
          <p className="text-sm text-muted-foreground">
            尚無篩選結果（尚未執行過批次篩選）。
          </p>
        )}

        {status === "done" && stocks.length > 0 && (
          <>
            {data?.screened_at && (
              <p className="text-xs text-muted-foreground">
                篩選時間：{new Date(data.screened_at).toLocaleString()}
              </p>
            )}
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-muted-foreground">
                  <tr className="text-left">
                    <th className="py-1 pr-2 text-right">排名</th>
                    <SortableTh sortKey="name" label="股票" align="left" activeKey={sortKey} dir={sortDir} onSort={requestSort} />
                    <SortableTh sortKey="price" label="現價" activeKey={sortKey} dir={sortDir} onSort={requestSort} />
                    <SortableTh sortKey="fcf_return" label="3年FCF報酬率均值" activeKey={sortKey} dir={sortDir} onSort={requestSort} />
                    <SortableTh sortKey="pb" label="股價淨值比" activeKey={sortKey} dir={sortDir} onSort={requestSort} />
                    <SortableTh sortKey="pe" label="本益比" activeKey={sortKey} dir={sortDir} onSort={requestSort} />
                    <SortableTh sortKey="yield" label="殖利率" activeKey={sortKey} dir={sortDir} onSort={requestSort} />
                    <SortableTh
                      sortKey="combined_score"
                      label={<>綜合分數<CombinedScoreExplainer /></>}
                      activeKey={sortKey}
                      dir={sortDir}
                      onSort={requestSort}
                    />
                  </tr>
                </thead>
                <tbody>
                  {sortedRows.map((row) => (
                    <tr key={row.symbol} className="border-t align-top">
                      <td className="py-1.5 pr-2 text-right tabular-nums text-muted-foreground">{row.rank}</td>
                      <td className="py-1.5 pr-2">
                        <Link href={`/analyze/${row.symbol}`} className="font-medium hover:underline">
                          {row.symbol} {row.name}
                        </Link>
                      </td>
                      <td className="py-1.5 pr-2 text-right tabular-nums">
                        {row.price != null ? row.price.toFixed(2) : "—"}
                      </td>
                      <td className="py-1.5 pr-2 text-right">
                        <FcfCell pct={row.fcf_return_3y_avg_pct} />
                      </td>
                      <td className="py-1.5 pr-2 text-right tabular-nums">
                        {row.pb_ratio.toFixed(2)}
                        <span className="text-muted-foreground"> (#{row.pb_rank})</span>
                      </td>
                      <td className="py-1.5 pr-2 text-right tabular-nums">
                        {row.pe_ratio.toFixed(2)}
                        <span className="text-muted-foreground"> (#{row.pe_rank})</span>
                      </td>
                      <td className="py-1.5 pr-2 text-right tabular-nums">
                        {row.dividend_yield_pct.toFixed(2)}%
                        <span className="text-muted-foreground"> (#{row.yield_rank})</span>
                      </td>
                      <td className="py-1.5 pr-2 text-right tabular-nums font-medium">{row.combined_score}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

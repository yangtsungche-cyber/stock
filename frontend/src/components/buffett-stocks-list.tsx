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

type BuffettStockRow = {
  rank: number;
  symbol: string;
  name: string;
  market: string;
  price: number | null;
  debt_ratio_latest_pct: number;
  debt_ratio_3y_avg_pct: number;
  debt_ratio_5y_avg_pct: number;
  roe_latest_pct: number;
  roe_3y_avg_pct: number;
  roe_5y_avg_pct: number;
  fcf_per_share_latest: number;
  fcf_per_share_3y_avg: number;
  fcf_per_share_5y_avg: number | null;
  volume_lots: number | null;
  dividend_yield_pct: number | null;
};

type BuffettStocksResponse = {
  screened_at: string | null;
  stocks: BuffettStockRow[];
};

// 只要掌握大致水準即可，小數點四捨五入取整數。
function Trio({ latest, y3, y5, unit }: { latest: number; y3: number; y5: number | null; unit: string }) {
  return (
    <span className="tabular-nums">
      {Math.round(latest)}{unit} / {Math.round(y3)}{unit} / {y5 != null ? `${Math.round(y5)}${unit}` : "—"}
    </span>
  );
}

function getSortValue(row: BuffettStockRow, key: string): string | number | null {
  switch (key) {
    case "name":
      return `${row.symbol} ${row.name}`;
    case "price":
      return row.price;
    case "debt_ratio":
      return row.debt_ratio_latest_pct;
    case "roe":
      return row.roe_latest_pct;
    case "fcf":
      return row.fcf_per_share_latest;
    case "volume":
      return row.volume_lots;
    case "yield":
      return row.dividend_yield_pct;
    default:
      return row.rank;
  }
}

function MethodologyExplainer() {
  return (
    <Dialog>
      <DialogTrigger render={<Button variant="ghost" size="icon-sm" className="ml-1 align-middle" />}>
        <Info className="size-3.5 text-muted-foreground" />
        <span className="sr-only">篩選條件說明</span>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>巴菲特選股條件是什麼？</DialogTitle>
        </DialogHeader>
        <div className="space-y-2 text-sm text-muted-foreground">
          <p>
            9 項條件必須<span className="font-medium text-foreground">全部同時達標</span>
            （不是勾選幾項就好）：
          </p>
          <ul className="list-inside list-disc space-y-1">
            <li>負債比率：近一年／近三年平均／近五年平均皆 &lt; 30%</li>
            <li>ROE：近一年／近三年平均／近五年平均皆 &gt; 15%</li>
            <li>每股自由現金流：近一年／近三年平均／近五年平均皆 &gt; 0</li>
          </ul>
          <p>
            3年/5年平均採一般算術平均（不是財報狗績優股清單用的幾何平均——負債比/ROE/每股FCF
            是水準型指標，不是複合成長率，用算術平均才正確）。清單依「5年平均ROE」由高到低排序，
            這只是顯示順序，不是篩選條件的一部分。
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function BuffettStocksList() {
  const [status, setStatus] = useState<"loading" | "done" | "error">("loading");
  const [data, setData] = useState<BuffettStocksResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchList() {
      setStatus("loading");
      setError(null);
      try {
        const res = await fetch(`${API_URL}/api/v1/buffett-stocks`);
        if (!res.ok) {
          const body = await res.json().catch(() => null);
          throw new Error(body?.detail ?? `HTTP ${res.status}`);
        }
        const body: BuffettStocksResponse = await res.json();
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
    <Card className="w-full max-w-5xl">
      <CardHeader>
        <CardTitle className="text-base">
          巴菲特選股清單
          <MethodologyExplainer />
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          負債比率、ROE、每股自由現金流三項指標，近一年／近三年平均／近五年平均共 9 項條件須全部達標。
          目前清單為財報狗官網「選股大師／巴菲特選股」實際篩選結果（已補上即時成交量），
          此處僅顯示最新一次匯入的快照。
        </p>

        {status === "loading" && <p className="text-sm text-muted-foreground">讀取中…</p>}
        {status === "error" && <p className="text-sm text-muted-foreground">讀取失敗：{error}</p>}

        {status === "done" && stocks.length === 0 && (
          <p className="text-sm text-muted-foreground">尚無篩選結果（尚未執行過批次篩選）。</p>
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
                    <SortableTh sortKey="debt_ratio" label="負債比率(1y/3y/5y)" activeKey={sortKey} dir={sortDir} onSort={requestSort} />
                    <SortableTh sortKey="roe" label="ROE(1y/3y/5y)" activeKey={sortKey} dir={sortDir} onSort={requestSort} />
                    <SortableTh sortKey="fcf" label="每股FCF(1y/3y/5y)" activeKey={sortKey} dir={sortDir} onSort={requestSort} />
                    <SortableTh sortKey="yield" label="殖利率" activeKey={sortKey} dir={sortDir} onSort={requestSort} />
                    <SortableTh sortKey="volume" label="成交量(張)" activeKey={sortKey} dir={sortDir} onSort={requestSort} />
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
                        <Trio latest={row.debt_ratio_latest_pct} y3={row.debt_ratio_3y_avg_pct} y5={row.debt_ratio_5y_avg_pct} unit="%" />
                      </td>
                      <td className="py-1.5 pr-2 text-right">
                        <Trio latest={row.roe_latest_pct} y3={row.roe_3y_avg_pct} y5={row.roe_5y_avg_pct} unit="%" />
                      </td>
                      <td className="py-1.5 pr-2 text-right">
                        <Trio latest={row.fcf_per_share_latest} y3={row.fcf_per_share_3y_avg} y5={row.fcf_per_share_5y_avg} unit="" />
                      </td>
                      <td className="py-1.5 pr-2 text-right tabular-nums">
                        {row.dividend_yield_pct != null ? `${row.dividend_yield_pct.toFixed(2)}%` : "—"}
                      </td>
                      <td className="py-1.5 pr-2 text-right tabular-nums">
                        {row.volume_lots != null ? row.volume_lots.toLocaleString(undefined, { maximumFractionDigits: 0 }) : "—"}
                      </td>
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

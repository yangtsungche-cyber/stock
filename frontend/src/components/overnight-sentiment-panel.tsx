"use client";

import Link from "next/link";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Suggestion = "add" | "hold" | "watch" | "trim";

type MacroComponent = {
  code: string;
  label: string;
  value: number;
  change_pct: number;
  score: number;
};

type MacroBlock = {
  has_data: boolean;
  error: string | null;
  as_of: string | null;
  components: MacroComponent[];
  score: number | null;
};

type StockRow = {
  symbol: string;
  name: string;
  error?: string;
  margin_score?: number | null;
  institutional_score?: number | null;
  score?: number | null;
  overall_score?: number | null;
  suggestion?: Suggestion | null;
  suggestion_label?: string | null;
};

// Same red=bullish/emerald=bearish/amber=neutral convention as the rest of this app.
const SUGGESTION_BADGE: Record<Suggestion, string> = {
  add: "bg-red-600 text-white",
  hold: "bg-amber-500 text-white",
  watch: "bg-amber-400 text-white",
  trim: "bg-emerald-600 text-white",
};

// Colored by this component's own `score` (bullish/bearish for the overall sentiment reading),
// not the raw sign of the % change — for USD/TWD and the 10Y yield a "+" move is bearish, so
// coloring by raw sign would show red (this app's bullish color) on a bearish move.
function ChangeCell({ pct, score }: { pct: number; score: number }) {
  const color = score > 50 ? "text-red-600" : score < 50 ? "text-emerald-600" : "text-muted-foreground";
  return (
    <span className={`tabular-nums font-medium ${color}`}>
      {pct > 0 ? "+" : ""}
      {pct}%
    </span>
  );
}

export function OvernightSentimentPanel() {
  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [macro, setMacro] = useState<MacroBlock | null>(null);
  const [stocks, setStocks] = useState<StockRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function loadSentiment() {
    setStatus("loading");
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/v1/overnight-sentiment`);
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      const body: { macro: MacroBlock; stocks: StockRow[] } = await res.json();
      setMacro(body.macro);
      setStocks(body.stocks);
      setStatus("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus("error");
    }
  }

  return (
    <Card className="w-full max-w-4xl">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base">第九層：晨間市場情緒（波段股池）</CardTitle>
        <Button onClick={loadSentiment} disabled={status === "loading"}>
          {status === "loading" ? "讀取中…" : "查看晨間情緒"}
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        {status === "idle" && (
          <p className="text-sm text-muted-foreground">
            結合隔夜美股／VIX／匯率總經數據與波段股池個股籌碼面，僅適用於自選股池中「波段」分類股票——核心長期持股不受短線隔夜雜訊影響。
          </p>
        )}
        {status === "loading" && <p className="text-sm text-muted-foreground">讀取中，請稍候…</p>}
        {status === "error" && <p className="text-sm text-muted-foreground">讀取失敗：{error}</p>}

        {status === "done" && macro && !macro.has_data && (
          <p className="text-sm text-muted-foreground">總經資料無法取得：{macro.error}（可能是網路限制，請改由可連線的網路重試）</p>
        )}

        {status === "done" && macro && macro.has_data && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-muted-foreground">
                <tr className="text-left">
                  <th className="py-1 pr-2">項目</th>
                  <th className="py-1 pr-2 text-right">數值</th>
                  <th className="py-1 pr-2 text-right">漲跌幅</th>
                  <th className="py-1 pr-2 text-right">分數</th>
                </tr>
              </thead>
              <tbody>
                {macro.components.map((c) => (
                  <tr key={c.code} className="border-t">
                    <td className="py-1.5 pr-2">{c.label}</td>
                    <td className="py-1.5 pr-2 text-right tabular-nums">{c.value}</td>
                    <td className="py-1.5 pr-2 text-right">
                      <ChangeCell pct={c.change_pct} score={c.score} />
                    </td>
                    <td className="py-1.5 pr-2 text-right tabular-nums">{c.score}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-sm text-muted-foreground">
              總經情緒分數：<span className="font-medium tabular-nums">{macro.score}</span> / 100
            </p>
          </div>
        )}

        {status === "done" && stocks.length === 0 && (
          <p className="text-sm text-muted-foreground">
            自選股池目前沒有「波段」分類的股票，請至「管理自選股池」新增或調整分類。
          </p>
        )}

        {status === "done" && stocks.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-muted-foreground">
                <tr className="text-left">
                  <th className="py-1 pr-2">股票</th>
                  <th className="py-1 pr-2 text-right">籌碼分數</th>
                  <th className="py-1 pr-2 text-right">綜合分數</th>
                  <th className="py-1 pr-2">建議</th>
                </tr>
              </thead>
              <tbody>
                {stocks.map((row) => (
                  <tr key={row.symbol} className="border-t align-top">
                    <td className="py-1.5 pr-2">
                      <Link href={`/analyze/${row.symbol}`} className="font-medium hover:underline">
                        {row.symbol} {row.name}
                      </Link>
                    </td>
                    {row.error ? (
                      <td className="py-1.5 pr-2 text-muted-foreground" colSpan={3}>
                        無法取得資料：{row.error}
                      </td>
                    ) : (
                      <>
                        <td className="py-1.5 pr-2 text-right tabular-nums">{row.score ?? "資料不足"}</td>
                        <td className="py-1.5 pr-2 text-right tabular-nums">
                          {row.overall_score ?? "—"}
                        </td>
                        <td className="py-1.5 pr-2">
                          {row.suggestion ? (
                            <Badge className={SUGGESTION_BADGE[row.suggestion]}>{row.suggestion_label}</Badge>
                          ) : (
                            <span className="text-muted-foreground">
                              {row.score == null ? "籌碼資料不足" : "總經資料不足"}
                            </span>
                          )}
                        </td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

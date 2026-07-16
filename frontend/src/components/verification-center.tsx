"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Display-only label mapping for decision.py's layer codes — same set as
// LAYER_LABELS there, duplicated here purely for UI text (not a threshold).
const LAYER_LABEL: Record<string, string> = {
  granville: "葛蘭碧法則",
  waves: "波浪理論",
  kd: "KD",
  macd: "MACD",
  bias: "均線乖離率",
  rsi: "RSI",
  volume: "成交量",
  margin: "融資融券",
  institutional: "三大法人",
};

type LayerStat = { fired_count: number; false_positive_rate: number | null };

type Stats = {
  total_records: number;
  matured_records: number;
  win_rate_strong_buy: number | null;
  win_rate_strong_buy_n: number;
  avg_return_bullish: number | null;
  avg_return_bullish_n: number;
  avoided_drop_rate_bearish: number | null;
  avoided_drop_rate_bearish_n: number;
  layer_false_positive_rate: Record<string, LayerStat>;
};

type HistoryRow = {
  id: number;
  stock_code: string;
  analysis_date: string;
  technical_score: number;
  technical_verdict: string;
  fundamental_rating: number | null;
  combined_label: string;
  confidence_pct: number;
  price_t0: number;
  price_t20: number | null;
  return_20d_pct: number | null;
  backfilled_at: string | null;
};

function StatCard({ label, value, n }: { label: string; value: string; n?: number }) {
  return (
    <div className="space-y-1">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="text-2xl font-semibold tabular-nums">{value}</p>
      {n !== undefined && <p className="text-xs text-muted-foreground">樣本數 {n}</p>}
    </div>
  );
}

function pct(v: number | null): string {
  return v === null ? "資料不足" : `${v}%`;
}

export function VerificationCenter() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [history, setHistory] = useState<HistoryRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [backfilling, setBackfilling] = useState(false);
  const [backfillMsg, setBackfillMsg] = useState<string | null>(null);

  function reload() {
    Promise.all([
      fetch(`${API_URL}/api/v1/verification/stats`).then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      }),
      fetch(`${API_URL}/api/v1/verification/history?limit=100`).then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      }),
    ])
      .then(([s, h]) => {
        setStats(s);
        setHistory(h);
      })
      .catch((err: Error) => setError(err.message));
  }

  useEffect(() => {
    reload();
  }, []);

  async function runBackfill() {
    setBackfilling(true);
    setBackfillMsg(null);
    try {
      const res = await fetch(`${API_URL}/api/v1/verification/backfill`, { method: "POST" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const body: { updated: number } = await res.json();
      setBackfillMsg(`已回填 ${body.updated} 筆紀錄`);
      reload();
    } catch (err) {
      setBackfillMsg(err instanceof Error ? `回填失敗：${err.message}` : String(err));
    } finally {
      setBackfilling(false);
    }
  }

  if (error) {
    return (
      <Card className="w-full max-w-4xl">
        <CardContent className="py-6 text-sm text-muted-foreground">無法取得資料：{error}</CardContent>
      </Card>
    );
  }

  return (
    <div className="w-full max-w-4xl space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">分析驗證中心</CardTitle>
          <Button onClick={runBackfill} disabled={backfilling} variant="outline" size="sm">
            {backfilling ? "回填中…" : "回填 20 天後報酬率"}
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            每次「開始 AI 掃描」都會留下一筆分析快照；滿 20 個交易日後即可回填當時判斷的實際
            表現，用以檢驗系統的訊號品質，而非單純相信分數。統計僅計入已滿 20 個交易日的紀錄。
          </p>
          {backfillMsg && <p className="text-sm text-muted-foreground">{backfillMsg}</p>}
          {!stats && <Skeleton className="h-24 w-full" />}
          {stats && (
            <>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <StatCard
                  label="強烈偏多勝率（20天後上漲）"
                  value={pct(stats.win_rate_strong_buy)}
                  n={stats.win_rate_strong_buy_n}
                />
                <StatCard
                  label="偏多訊號平均報酬率"
                  value={stats.avg_return_bullish === null ? "資料不足" : `${stats.avg_return_bullish}%`}
                  n={stats.avg_return_bullish_n}
                />
                <StatCard
                  label="偏空訊號成功避開下跌比例"
                  value={pct(stats.avoided_drop_rate_bearish)}
                  n={stats.avoided_drop_rate_bearish_n}
                />
                <StatCard
                  label="已滿20天／總紀錄數"
                  value={`${stats.matured_records} / ${stats.total_records}`}
                />
              </div>
              {stats.total_records === 0 && (
                <p className="text-sm text-muted-foreground">
                  目前尚無任何紀錄。請先至首頁執行「開始 AI 掃描」，累積分析快照。
                </p>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {stats && Object.keys(stats.layer_false_positive_rate).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">各指標假陽性率</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm">
              {Object.entries(stats.layer_false_positive_rate).map(([layer, s]) => (
                <li key={layer} className="flex items-center justify-between border-t pt-2 first:border-t-0 first:pt-0">
                  <span>{LAYER_LABEL[layer] ?? layer}</span>
                  <span className="text-muted-foreground">
                    {s.fired_count === 0 ? "尚無已滿20天的訊號樣本" : `假陽性率 ${s.false_positive_rate}%（${s.fired_count} 筆訊號）`}
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">分析歷史紀錄</CardTitle>
        </CardHeader>
        <CardContent>
          {!history && <Skeleton className="h-40 w-full" />}
          {history && history.length === 0 && (
            <p className="text-sm text-muted-foreground">目前尚無任何紀錄。</p>
          )}
          {history && history.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-muted-foreground">
                  <tr className="text-left">
                    <th className="py-1 pr-2">日期</th>
                    <th className="py-1 pr-2">股票</th>
                    <th className="py-1 pr-2 text-right">技術分數</th>
                    <th className="py-1 pr-2 text-right">T0 收盤</th>
                    <th className="py-1 pr-2 text-right">T+20 收盤</th>
                    <th className="py-1 pr-2 text-right">20天報酬率</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((row) => (
                    <tr key={row.id} className="border-t">
                      <td className="py-1.5 pr-2 text-muted-foreground">{row.analysis_date}</td>
                      <td className="py-1.5 pr-2">
                        <Link href={`/analyze/${row.stock_code}`} className="font-medium hover:underline">
                          {row.stock_code}
                        </Link>
                      </td>
                      <td className="py-1.5 pr-2 text-right tabular-nums">
                        {row.technical_score > 0 ? "+" : ""}
                        {row.technical_score}
                      </td>
                      <td className="py-1.5 pr-2 text-right tabular-nums">{row.price_t0}</td>
                      <td className="py-1.5 pr-2 text-right tabular-nums">{row.price_t20 ?? "—"}</td>
                      <td className="py-1.5 pr-2 text-right tabular-nums">
                        {row.return_20d_pct === null ? (
                          <Badge variant="secondary">尚未滿20天</Badge>
                        ) : (
                          <span className={row.return_20d_pct >= 0 ? "text-red-600" : "text-emerald-600"}>
                            {row.return_20d_pct > 0 ? "+" : ""}
                            {row.return_20d_pct}%
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

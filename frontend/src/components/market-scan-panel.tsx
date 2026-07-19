"use client";

import Link from "next/link";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { InfoTip } from "@/components/info-tip";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Verdict = "strong_buy" | "buy" | "neutral" | "sell" | "strong_sell";

type ScanRow = {
  symbol: string;
  name: string;
  category: string;
  source: "watchlist" | "candidate_pool" | "both";
  error?: string;
  technical_score?: number;
  technical_verdict?: Verdict;
  technical_verdict_label?: string;
  grade?: "A" | "B" | "C" | "D";
  confidence_pct?: number;
  fundamental_rating?: number | null;
  fundamental_rating_label?: string | null;
  combined_label?: string;
  has_fundamental_data?: boolean;
};

// Same convention as DecisionSummaryPanel: red = bullish, emerald = bearish, amber = neutral.
const VERDICT_DOT: Record<Verdict, string> = {
  strong_buy: "bg-red-600",
  buy: "bg-red-400",
  neutral: "bg-amber-500",
  sell: "bg-emerald-400",
  strong_sell: "bg-emerald-600",
};

const SOURCE_LABEL: Record<ScanRow["source"], string> = {
  watchlist: "自選股",
  candidate_pool: "候選池",
  both: "自選股＋候選池",
};

// 訊號品質分級不是方向性判斷，刻意不沿用紅漲/綠跌配色（同 DecisionSummaryPanel）。
const GRADE_BADGE_COLOR: Record<"A" | "B" | "C" | "D", string> = {
  A: "bg-green-600 text-white",
  B: "bg-blue-600 text-white",
  C: "bg-amber-500 text-white",
  D: "bg-zinc-500 text-white",
};

function ScoreCell({ score }: { score: number }) {
  const color = score > 0 ? "text-red-600" : score < 0 ? "text-emerald-600" : "text-muted-foreground";
  return (
    <span className={`tabular-nums font-medium ${color}`}>
      {score > 0 ? "+" : ""}
      {score}
    </span>
  );
}

export function MarketScanPanel() {
  const [status, setStatus] = useState<"idle" | "scanning" | "done" | "error">("idle");
  const [rows, setRows] = useState<ScanRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function startScan() {
    setStatus("scanning");
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/v1/scan`, { method: "POST" });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      const body: { count: number; results: ScanRow[] } = await res.json();
      setRows(body.results);
      setStatus("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus("error");
    }
  }

  return (
    <Card className="w-full max-w-4xl">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base">AI 市場總表</CardTitle>
        <Button onClick={startScan} disabled={status === "scanning"}>
          {status === "scanning" ? "掃描中…" : "開始 AI 掃描"}
        </Button>
      </CardHeader>
      <CardContent>
        {status === "idle" && (
          <p className="text-sm text-muted-foreground">
            合併自選股池與基本面候選池，對每檔股票跑完整技術面＋基本面分析，產生總覽表。
          </p>
        )}
        {status === "scanning" && (
          <p className="text-sm text-muted-foreground">
            掃描中，依股票數量約需 5 分鐘，請稍候…
          </p>
        )}
        {status === "error" && <p className="text-sm text-muted-foreground">掃描失敗：{error}</p>}
        {status === "done" && rows.length === 0 && (
          <p className="text-sm text-muted-foreground">
            自選股池與候選池目前皆為空，請先至「管理自選股池」新增，或執行候選池篩選批次。
          </p>
        )}
        {status === "done" && rows.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-muted-foreground">
                <tr className="text-left">
                  <th className="py-1 pr-2">股票</th>
                  <th className="py-1 pr-2">來源</th>
                  <th className="py-1 pr-2 text-right">
                    技術分數
                    <InfoTip title="技術分數">
                      <p>
                        綜合「八層分析」（葛蘭碧、KD、MACD、乖離率、RSI、成交量、融資融券、法人買賣、波浪）算出的技術面總分，範圍
                        -100～+100。
                      </p>
                      <p>正值代表偏多訊號較強，負值代表偏空訊號較強；數字大小反映訊號強度，不代表預期漲跌幅度。</p>
                    </InfoTip>
                  </th>
                  <th className="py-1 pr-2 text-center">
                    訊號品質
                    <InfoTip title="訊號品質（A / B / C / D）">
                      <p>衡量技術分數的「訊號廣度」夠不夠——八層分析裡有幾層實際觸發出訊號（覆蓋率）。覆蓋率越高，這個分數才越可信：</p>
                      <ul className="list-disc space-y-1 pl-4">
                        <li>A 級：覆蓋率 ≥ 70%，訊號廣泛一致，可信度高。</li>
                        <li>B 級：50% ～ 70%，尚可參考。</li>
                        <li>C 級：40% ～ 50%，訊號較窄，建議謹慎看待。</li>
                        <li>D 級：覆蓋率 &lt; 40%（系統會把方向性判斷直接降為中性），或原本就是中性——代表現在不建議把它當成方向性訊號。</li>
                      </ul>
                    </InfoTip>
                  </th>
                  <th className="py-1 pr-2 text-right">
                    基本面★
                    <InfoTip title="基本面★">
                      <p>
                        依據財報體質檢查清單（獲利能力、成長性、股東回報等指標）算出的 1.0～5.0
                        顆星評分：1 + 達標項目比例 × 4。
                      </p>
                      <p>星數越高代表通過越多項基本面檢核，而非「買進評等」。</p>
                    </InfoTip>
                  </th>
                  <th className="py-1 pr-2 text-right">信心%</th>
                  <th className="py-1 pr-2 text-center">燈號</th>
                  <th className="py-1 pr-2">建議</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.symbol} className="border-t align-top">
                    <td className="py-1.5 pr-2">
                      <Link href={`/analyze/${row.symbol}`} className="font-medium hover:underline">
                        {row.symbol} {row.name}
                      </Link>
                    </td>
                    <td className="py-1.5 pr-2">
                      <Badge variant="secondary">{SOURCE_LABEL[row.source]}</Badge>
                    </td>
                    {row.error ? (
                      <td className="py-1.5 pr-2 text-muted-foreground" colSpan={6}>
                        無法取得資料：{row.error}
                      </td>
                    ) : (
                      <>
                        <td className="py-1.5 pr-2 text-right">
                          <ScoreCell score={row.technical_score ?? 0} />
                        </td>
                        <td className="py-1.5 pr-2 text-center">
                          {row.grade ? (
                            <Badge className={GRADE_BADGE_COLOR[row.grade]}>{row.grade}</Badge>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </td>
                        <td className="py-1.5 pr-2 text-right tabular-nums">
                          {row.fundamental_rating != null ? `${row.fundamental_rating.toFixed(1)} / 5.0` : "—"}
                        </td>
                        <td className="py-1.5 pr-2 text-right tabular-nums">{row.confidence_pct ?? 0}%</td>
                        <td className="py-1.5 pr-2">
                          <div className="flex justify-center">
                            <span
                              className={`h-3 w-3 rounded-full ${VERDICT_DOT[row.technical_verdict ?? "neutral"]}`}
                              title={row.technical_verdict_label}
                            />
                          </div>
                        </td>
                        <td className="py-1.5 pr-2">{row.combined_label}</td>
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

"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { InfoTip } from "@/components/info-tip";
import { SortableTh } from "@/components/sortable-th";
import { useSortableData } from "@/lib/use-sortable-data";
import { TeacherRecommendationsRefresh } from "@/components/teacher-recommendations-refresh";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Verdict = "strong_buy" | "buy" | "neutral" | "sell" | "strong_sell";

// 跟 MarketScanPanel/DecisionSummaryPanel 同一套配色慣例：紅=偏多、綠=偏空、琥珀=中性。
const VERDICT_DOT: Record<Verdict, string> = {
  strong_buy: "bg-red-600",
  buy: "bg-red-400",
  neutral: "bg-amber-500",
  sell: "bg-emerald-400",
  strong_sell: "bg-emerald-600",
};

const GRADE_BADGE_COLOR: Record<"A" | "B" | "C" | "D", string> = {
  A: "bg-green-600 text-white",
  B: "bg-blue-600 text-white",
  C: "bg-amber-500 text-white",
  D: "bg-zinc-500 text-white",
};

function ScoreCell({ score }: { score: number | null }) {
  if (score == null) return <span className="text-muted-foreground">—</span>;
  const color = score > 0 ? "text-red-600" : score < 0 ? "text-emerald-600" : "text-muted-foreground";
  return (
    <span className={`tabular-nums font-medium ${color}`}>
      {score > 0 ? "+" : ""}
      {score}
    </span>
  );
}

function Stars({ value }: { value: number | null }) {
  if (value == null) return <span className="text-muted-foreground">—</span>;
  const full = Math.floor(value);
  const half = value - full >= 0.5;
  return (
    <span className="text-amber-500" title={`${value} / 5.0`}>
      {"★".repeat(full)}
      {half ? "☆" : ""}
    </span>
  );
}

type Recommendation = {
  id: number;
  symbol: string;
  name: string;
  teacher_rank: number | null;
  main_industry: string | null;
  long_term_rating: number | null;
  investment_category: string | null;
  ai_benefit_rating: number | null;
  volatility: string | null;
  suitable_strategy: string | null;
  updated_at: string | null;
  error?: string;
  close?: number;
  technical_score?: number;
  technical_verdict?: Verdict;
  technical_verdict_label?: string;
  grade?: "A" | "B" | "C" | "D";
  confidence_pct?: number;
  fundamental_rating?: number | null;
  fundamental_rating_label?: string | null;
  combined_label?: string;
  composite_score: number | null;
  quality_available: boolean;
  system_rank: number | null;
};

const CACHE_KEY = "teacher-recommendations-cache";

type Cached = { rows: Recommendation[]; cachedAt: string };

function readCache(): Cached | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(CACHE_KEY);
    return raw ? (JSON.parse(raw) as Cached) : null;
  } catch {
    return null;
  }
}

function writeCache(rows: Recommendation[]): string {
  const cachedAt = new Date().toISOString();
  try {
    window.sessionStorage.setItem(CACHE_KEY, JSON.stringify({ rows, cachedAt }));
  } catch {
    // sessionStorage unavailable — skip caching, next mount just recomputes
  }
  return cachedAt;
}

function getSortValue(row: Recommendation, key: string): string | number | null | undefined {
  switch (key) {
    case "symbol": return `${row.symbol}${row.name}`;
    default: return (row as unknown as Record<string, string | number | null | undefined>)[key];
  }
}

function AddEntryDialog({ onAdded }: { onAdded: () => void }) {
  const [open, setOpen] = useState(false);
  const [symbol, setSymbol] = useState("");
  const [resolvedName, setResolvedName] = useState<string | null>(null);
  const [teacherRank, setTeacherRank] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [resolving, setResolving] = useState(false);

  async function resolveName() {
    if (!symbol.trim()) return;
    setResolving(true);
    setResolvedName(null);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/v1/stocks/${symbol.trim().toUpperCase()}/info`);
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      const body: { name: string } = await res.json();
      setResolvedName(body.name);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setResolving(false);
    }
  }

  async function submit() {
    if (!resolvedName) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/v1/teacher-recommendations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: symbol.trim().toUpperCase(),
          name: resolvedName,
          teacher_rank: teacherRank.trim() ? Number(teacherRank) : null,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      setSymbol("");
      setResolvedName(null);
      setTeacherRank("");
      setOpen(false);
      onAdded();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" />}>新增股票</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>新增老師建議股票</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">股票代號</label>
            <div className="flex gap-2">
              <Input
                value={symbol}
                onChange={(e) => { setSymbol(e.target.value); setResolvedName(null); }}
                placeholder="例如 2330"
              />
              <Button size="sm" variant="outline" onClick={resolveName} disabled={resolving || !symbol.trim()}>
                {resolving ? "查詢中…" : "查詢名稱"}
              </Button>
            </div>
            {resolvedName && <p className="text-sm text-muted-foreground">名稱：{resolvedName}</p>}
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">老師原始排名（選填）</label>
            <Input value={teacherRank} onChange={(e) => setTeacherRank(e.target.value)} placeholder="例如 1" />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button onClick={submit} disabled={submitting || !resolvedName}>
            {submitting ? "新增中…" : "新增"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function TeacherRecommendationsManager() {
  const [rows, setRows] = useState<Recommendation[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cachedAt, setCachedAt] = useState<string | null>(null);
  const [pdfStatus, setPdfStatus] = useState<"idle" | "generating" | "error">("idle");
  const [pdfError, setPdfError] = useState<string | null>(null);

  async function fetchDashboard() {
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/v1/teacher-recommendations`);
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      const body: { recommendations: Recommendation[] } = await res.json();
      setRows(body.recommendations);
      setCachedAt(writeCache(body.recommendations));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => {
    const cached = readCache();
    if (cached) {
      setRows(cached.rows);
      setCachedAt(cached.cachedAt);
    } else {
      fetchDashboard();
    }
  }, []);

  async function remove(row: Recommendation) {
    if (!window.confirm(`確定要移除 ${row.symbol} ${row.name}？`)) return;
    await fetch(`${API_URL}/api/v1/teacher-recommendations/${row.id}`, { method: "DELETE" });
    fetchDashboard();
  }

  async function downloadPdf() {
    setPdfStatus("generating");
    setPdfError(null);
    try {
      const res = await fetch(`${API_URL}/api/v1/teacher-recommendations/report.pdf`);
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "老師建議清單.pdf";
      a.click();
      URL.revokeObjectURL(url);
      setPdfStatus("idle");
    } catch (err) {
      setPdfError(err instanceof Error ? err.message : String(err));
      setPdfStatus("error");
    }
  }

  const { sortedRows, sortKey, sortDir, requestSort } = useSortableData(
    rows ?? [],
    getSortValue,
    { key: "system_rank", dir: "asc" }
  );

  return (
    <div className="flex w-full max-w-6xl flex-col gap-4">
      <Card className="w-full">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">
            老師建議清單
            <InfoTip title="系統排名怎麼算？">
              <p>系統排名 = 0.6 × 技術分數（decision.py，進場時機）+ 0.4 × AI 綜合評判品質星等
              （長期評價與 AI 受惠程度平均，換算成 -100..+100）。</p>
              <p>老師原始排名只作參考，不納入計算——目的是提供跟老師靜態長期評價「不同角度」的
              進場時機判斷。剛新增、尚無 AI 評等的股票，系統排名暫以技術分數為準。</p>
            </InfoTip>
          </CardTitle>
          <div className="flex items-center gap-2">
            {cachedAt && (
              <span className="text-xs text-muted-foreground">
                上次更新：{new Date(cachedAt).toLocaleTimeString("zh-TW")}
              </span>
            )}
            <Button size="sm" variant="outline" onClick={fetchDashboard}>重新整理</Button>
            <Button size="sm" variant="outline" onClick={downloadPdf} disabled={pdfStatus === "generating"}>
              {pdfStatus === "generating" ? "產生中…" : "下載 PDF"}
            </Button>
            <AddEntryDialog onAdded={fetchDashboard} />
          </div>
        </CardHeader>
        <CardContent>
          {error && <p className="text-sm text-muted-foreground">無法取得資料：{error}</p>}
          {pdfError && <p className="text-sm text-destructive">PDF 產生失敗：{pdfError}</p>}
          {!rows && !error && <Skeleton className="h-64 w-full" />}
          {rows && rows.length === 0 && (
            <p className="text-sm text-muted-foreground">清單是空的，點右上角新增股票。</p>
          )}
          {rows && rows.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-muted-foreground">
                  <tr>
                    <SortableTh sortKey="system_rank" label="排名" activeKey={sortKey} dir={sortDir} onSort={requestSort} />
                    <th className="py-1 pr-2 text-right text-muted-foreground">老師排名</th>
                    <SortableTh sortKey="symbol" label="股票" activeKey={sortKey} dir={sortDir} onSort={requestSort} align="left" />
                    <SortableTh sortKey="close" label="現價" activeKey={sortKey} dir={sortDir} onSort={requestSort} />
                    <th className="py-1 pr-2 text-left text-muted-foreground">主要產業</th>
                    <th className="py-1 pr-2 text-left text-muted-foreground">長期評價</th>
                    <th className="py-1 pr-2 text-left text-muted-foreground">投資分類</th>
                    <th className="py-1 pr-2 text-left text-muted-foreground">AI受惠</th>
                    <th className="py-1 pr-2 text-left text-muted-foreground">波動</th>
                    <th className="py-1 pr-2 text-left text-muted-foreground">策略</th>
                    <SortableTh sortKey="technical_score" label="技術分數" activeKey={sortKey} dir={sortDir} onSort={requestSort} />
                    <th className="py-1 pr-2 text-center text-muted-foreground">分級</th>
                    <SortableTh sortKey="confidence_pct" label="訊號品質" activeKey={sortKey} dir={sortDir} onSort={requestSort} />
                    <th className="py-1 pr-2 text-left text-muted-foreground">基本面</th>
                    <SortableTh sortKey="composite_score" label="綜合分數" activeKey={sortKey} dir={sortDir} onSort={requestSort} />
                    <th className="py-1 pr-2 text-right text-muted-foreground">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedRows.map((row) => (
                    <tr key={row.id} className="border-t">
                      <td className="py-1.5 pr-2 text-right tabular-nums">{row.system_rank ?? "—"}</td>
                      <td className="py-1.5 pr-2 text-right tabular-nums text-muted-foreground">
                        {row.teacher_rank ?? "—"}
                      </td>
                      <td className="py-1.5 pr-2">
                        <Link href={`/analyze/${row.symbol}`} className="font-medium hover:underline">
                          {row.symbol} {row.name}
                        </Link>
                        {!row.quality_available && !row.error && (
                          <Badge variant="secondary" className="ml-1 align-middle text-[10px]">
                            尚無 AI 評等
                          </Badge>
                        )}
                      </td>
                      {row.error ? (
                        <td className="py-1.5 pr-2 text-muted-foreground" colSpan={12}>
                          無法取得分析資料：{row.error}
                        </td>
                      ) : (
                        <>
                          <td className="py-1.5 pr-2 text-right tabular-nums">{row.close ?? "—"}</td>
                          <td className="py-1.5 pr-2">{row.main_industry ?? "—"}</td>
                          <td className="py-1.5 pr-2"><Stars value={row.long_term_rating} /></td>
                          <td className="py-1.5 pr-2">{row.investment_category ?? "—"}</td>
                          <td className="py-1.5 pr-2"><Stars value={row.ai_benefit_rating} /></td>
                          <td className="py-1.5 pr-2">{row.volatility ?? "—"}</td>
                          <td className="py-1.5 pr-2">{row.suitable_strategy ?? "—"}</td>
                          <td className="py-1.5 pr-2 text-right"><ScoreCell score={row.technical_score ?? null} /></td>
                          <td className="py-1.5 pr-2 text-center">
                            {row.grade ? (
                              <Badge className={GRADE_BADGE_COLOR[row.grade]}>{row.grade}</Badge>
                            ) : (
                              <span className="text-muted-foreground">—</span>
                            )}
                          </td>
                          <td className="py-1.5 pr-2 text-right tabular-nums">{row.confidence_pct ?? 0}%</td>
                          <td className="py-1.5 pr-2">
                            {row.fundamental_rating != null ? `${row.fundamental_rating.toFixed(1)} / 5.0` : "—"}
                          </td>
                          <td className="py-1.5 pr-2 text-right">
                            <div className="flex items-center justify-end gap-1">
                              <span className={`h-2.5 w-2.5 rounded-full ${VERDICT_DOT[row.technical_verdict ?? "neutral"]}`} />
                              <ScoreCell score={row.composite_score} />
                            </div>
                          </td>
                        </>
                      )}
                      <td className="py-1.5 pr-2 text-right">
                        <Button size="sm" variant="destructive" onClick={() => remove(row)}>
                          刪除
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <TeacherRecommendationsRefresh onSaved={fetchDashboard} />
    </div>
  );
}

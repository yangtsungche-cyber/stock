"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { SUGGESTION_BADGE, type Suggestion } from "@/lib/suggestion-badge";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// The dashboard takes minutes to compute (a live technical+fundamental pass over every holding),
// so re-running it every time this page remounts — e.g. navigating to a stock's detail page and
// back — would be wasteful. Cache the last result in sessionStorage; only "重新整理" (or the very
// first visit this session) triggers a real recompute.
const CACHE_KEY = "portfolio-dashboard-cache";

type CachedDashboard = { holdings: Holding[]; cachedAt: string };

function readCache(): CachedDashboard | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(CACHE_KEY);
    return raw ? (JSON.parse(raw) as CachedDashboard) : null;
  } catch {
    return null;
  }
}

function writeCache(holdings: Holding[]): string {
  const cachedAt = new Date().toISOString();
  try {
    window.sessionStorage.setItem(CACHE_KEY, JSON.stringify({ holdings, cachedAt }));
  } catch {
    // sessionStorage unavailable — just skip caching, next mount will recompute
  }
  return cachedAt;
}

type PreviewRow = {
  symbol: string;
  name: string;
  market: string;
  shares: number;
  cost_basis: number;
};

type Holding = {
  symbol: string;
  name: string;
  market: string;
  shares: number;
  cost_basis: number;
  quality_badge: "績優" | "績巴" | "巴特" | null;
  error?: string;
  close?: number;
  market_value?: number;
  unrealized_pl?: number;
  unrealized_pl_pct?: number | null;
  weight_pct?: number | null;
  technical_score?: number;
  technical_verdict_label?: string;
  fundamental_rating?: number | null;
  fundamental_rating_label?: string | null;
  combined_label?: string;
  suggestion?: Suggestion;
  suggestion_label?: string;
};

// List-membership tags, not a bullish/bearish directional signal — deliberately does not reuse
// the red=bullish/emerald=bearish convention (would be misleading for a membership tag).
const QUALITY_BADGE_COLOR: Record<"績優" | "績巴" | "巴特", string> = {
  績巴: "bg-red-600 text-white",
  績優: "bg-amber-500 text-white",
  巴特: "bg-blue-600 text-white",
};

function PlCell({ value }: { value: number }) {
  const color = value > 0 ? "text-red-600" : value < 0 ? "text-emerald-600" : "text-muted-foreground";
  return (
    <span className={`tabular-nums font-medium ${color}`}>
      {value > 0 ? "+" : ""}
      {value.toLocaleString(undefined, { maximumFractionDigits: 0 })}
    </span>
  );
}

function ScoreCell({ score }: { score: number }) {
  const color = score > 0 ? "text-red-600" : score < 0 ? "text-emerald-600" : "text-muted-foreground";
  return (
    <span className={`tabular-nums font-medium ${color}`}>
      {score > 0 ? "+" : ""}
      {score}
    </span>
  );
}

export function PortfolioDashboard() {
  const [showPaste, setShowPaste] = useState(false);
  const [pasteText, setPasteText] = useState("");
  const [parseStatus, setParseStatus] = useState<"idle" | "parsing" | "done" | "error">("idle");
  const [parseError, setParseError] = useState<string | null>(null);
  const [previewRows, setPreviewRows] = useState<PreviewRow[]>([]);
  const [previewErrors, setPreviewErrors] = useState<string[]>([]);
  const [importStatus, setImportStatus] = useState<"idle" | "importing" | "done" | "error">("idle");

  const [dashboardStatus, setDashboardStatus] = useState<"loading" | "done" | "error">("loading");
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [dashboardError, setDashboardError] = useState<string | null>(null);
  const [cachedAt, setCachedAt] = useState<string | null>(null);

  async function fetchDashboard() {
    setDashboardStatus("loading");
    setDashboardError(null);
    try {
      const res = await fetch(`${API_URL}/api/v1/portfolio`);
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      const body: { holdings: Holding[] } = await res.json();
      setHoldings(body.holdings);
      setCachedAt(writeCache(body.holdings));
      setDashboardStatus("done");
    } catch (err) {
      setDashboardError(err instanceof Error ? err.message : String(err));
      setDashboardStatus("error");
    }
  }

  useEffect(() => {
    const cached = readCache();
    if (cached) {
      setHoldings(cached.holdings);
      setCachedAt(cached.cachedAt);
      setDashboardStatus("done");
    } else {
      fetchDashboard();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function parseText() {
    setParseStatus("parsing");
    setParseError(null);
    try {
      const res = await fetch(`${API_URL}/api/v1/portfolio/parse`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: pasteText }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      const body: { rows: PreviewRow[]; errors: string[] } = await res.json();
      setPreviewRows(body.rows);
      setPreviewErrors(body.errors);
      setParseStatus("done");
    } catch (err) {
      setParseError(err instanceof Error ? err.message : String(err));
      setParseStatus("error");
    }
  }

  function updatePreviewRow(index: number, field: "shares" | "cost_basis", value: string) {
    setPreviewRows((rows) =>
      rows.map((row, i) => (i === index ? { ...row, [field]: Number(value) } : row))
    );
  }

  const validHoldings = holdings.filter((h) => !h.error && h.market_value != null && h.unrealized_pl != null);
  const totalMarketValue = validHoldings.reduce((sum, h) => sum + (h.market_value ?? 0), 0);
  const totalUnrealizedPl = validHoldings.reduce((sum, h) => sum + (h.unrealized_pl ?? 0), 0);
  const totalCostBasis = totalMarketValue - totalUnrealizedPl;
  const totalUnrealizedPlPct = totalCostBasis !== 0 ? (totalUnrealizedPl / totalCostBasis) * 100 : null;

  async function confirmImport() {
    setImportStatus("importing");
    try {
      const res = await fetch(`${API_URL}/api/v1/portfolio/import`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rows: previewRows }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      setImportStatus("done");
      setShowPaste(false);
      setPasteText("");
      setParseStatus("idle");
      setPreviewRows([]);
      setPreviewErrors([]);
      await fetchDashboard();
    } catch (err) {
      setParseError(err instanceof Error ? err.message : String(err));
      setImportStatus("error");
    }
  }

  return (
    <div className="w-full max-w-5xl space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">持股庫存匯入</CardTitle>
          <Button variant="secondary" onClick={() => setShowPaste((v) => !v)}>
            {showPaste ? "收起" : "更新庫存"}
          </Button>
        </CardHeader>
        {showPaste && (
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">
              貼上辨識結果，格式：<code className="rounded bg-muted px-1">股票代號,股數,成本均價</code>，一行一檔。
              每次匯入視為完整的目前持股快照，會整批取代先前的庫存資料。
            </p>
            <textarea
              className="min-h-40 w-full rounded-lg border border-input bg-transparent p-3 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
              placeholder={"2330,2043,1895.73\n0050,1000,102.5\n..."}
              value={pasteText}
              onChange={(e) => setPasteText(e.target.value)}
            />
            <Button onClick={parseText} disabled={parseStatus === "parsing" || !pasteText.trim()}>
              {parseStatus === "parsing" ? "解析中…" : "解析"}
            </Button>
            {parseStatus === "error" && <p className="text-sm text-muted-foreground">解析失敗：{parseError}</p>}

            {parseStatus === "done" && (
              <div className="space-y-3">
                {previewErrors.length > 0 && (
                  <div className="rounded-lg border border-destructive/50 p-2 text-sm text-destructive">
                    {previewErrors.map((e, i) => (
                      <p key={i}>{e}</p>
                    ))}
                  </div>
                )}
                {previewRows.length === 0 && (
                  <p className="text-sm text-muted-foreground">沒有解析出任何一筆有效資料。</p>
                )}
                {previewRows.length > 0 && (
                  <>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead className="text-muted-foreground">
                          <tr className="text-left">
                            <th className="py-1 pr-2">股票</th>
                            <th className="py-1 pr-2 text-right">股數</th>
                            <th className="py-1 pr-2 text-right">成本均價</th>
                          </tr>
                        </thead>
                        <tbody>
                          {previewRows.map((row, i) => (
                            <tr key={row.symbol} className="border-t">
                              <td className="py-1.5 pr-2">
                                {row.symbol} {row.name}（{row.market}）
                              </td>
                              <td className="py-1.5 pr-2 text-right">
                                <Input
                                  className="ml-auto w-28 text-right"
                                  type="number"
                                  value={row.shares}
                                  onChange={(e) => updatePreviewRow(i, "shares", e.target.value)}
                                />
                              </td>
                              <td className="py-1.5 pr-2 text-right">
                                <Input
                                  className="ml-auto w-28 text-right"
                                  type="number"
                                  value={row.cost_basis}
                                  onChange={(e) => updatePreviewRow(i, "cost_basis", e.target.value)}
                                />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <Button onClick={confirmImport} disabled={importStatus === "importing"}>
                      {importStatus === "importing" ? "匯入中…" : `確認匯入（${previewRows.length} 檔）`}
                    </Button>
                    {importStatus === "error" && (
                      <p className="text-sm text-muted-foreground">匯入失敗：{parseError}</p>
                    )}
                  </>
                )}
              </div>
            )}
          </CardContent>
        )}
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">持股盤點與建議</CardTitle>
          <div className="flex items-center gap-2">
            {cachedAt && dashboardStatus === "done" && (
              <span className="text-xs text-muted-foreground">
                上次更新：{new Date(cachedAt).toLocaleTimeString()}
              </span>
            )}
            <Button onClick={fetchDashboard} disabled={dashboardStatus === "loading"} variant="secondary">
              {dashboardStatus === "loading" ? "計算中…" : "重新整理"}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {dashboardStatus === "loading" && (
            <p className="text-sm text-muted-foreground">
              正在對每檔持股跑技術面/基本面即時分析，依持股數量約需數分鐘，請稍候…
            </p>
          )}
          {dashboardStatus === "error" && <p className="text-sm text-muted-foreground">讀取失敗：{dashboardError}</p>}
          {dashboardStatus === "done" && holdings.length === 0 && (
            <p className="text-sm text-muted-foreground">尚無庫存資料，請先點上方「更新庫存」匯入。</p>
          )}
          {dashboardStatus === "done" && holdings.length > 0 && (
            <>
              <div className="mb-3 flex flex-wrap gap-6 text-sm">
                <div>
                  <span className="text-muted-foreground">總市值　</span>
                  <span className="font-medium tabular-nums">
                    {totalMarketValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                  </span>
                </div>
                <div>
                  <span className="text-muted-foreground">總損益　</span>
                  <PlCell value={totalUnrealizedPl} />
                </div>
                <div>
                  <span className="text-muted-foreground">總損益%　</span>
                  {totalUnrealizedPlPct != null ? (
                    <span
                      className={`tabular-nums font-medium ${
                        totalUnrealizedPlPct > 0
                          ? "text-red-600"
                          : totalUnrealizedPlPct < 0
                            ? "text-emerald-600"
                            : "text-muted-foreground"
                      }`}
                    >
                      {totalUnrealizedPlPct > 0 ? "+" : ""}
                      {totalUnrealizedPlPct.toFixed(2)}%
                    </span>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </div>
              </div>
              <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-muted-foreground">
                  <tr className="text-left">
                    <th className="py-1 pr-2">股票</th>
                    <th className="py-1 pr-2 text-right">股數</th>
                    <th className="py-1 pr-2 text-right">成本均價</th>
                    <th className="py-1 pr-2 text-right">現價</th>
                    <th className="py-1 pr-2 text-right">市值</th>
                    <th className="py-1 pr-2 text-right">權重%</th>
                    <th className="py-1 pr-2 text-right">損益</th>
                    <th className="py-1 pr-2 text-right">損益%</th>
                    <th className="py-1 pr-2 text-right">技術分數</th>
                    <th className="py-1 pr-2 text-right">基本面★</th>
                    <th className="py-1 pr-2 text-center">財報狗清單</th>
                    <th className="py-1 pr-2">建議</th>
                  </tr>
                </thead>
                <tbody>
                  {holdings.map((h) => (
                    <tr key={h.symbol} className="border-t align-top">
                      <td className="py-1.5 pr-2">
                        <Link href={`/analyze/${h.symbol}`} className="font-medium hover:underline">
                          {h.symbol} {h.name}
                        </Link>
                      </td>
                      <td className="py-1.5 pr-2 text-right tabular-nums">{h.shares.toLocaleString()}</td>
                      <td className="py-1.5 pr-2 text-right tabular-nums">{h.cost_basis.toFixed(2)}</td>
                      {h.error ? (
                        <td className="py-1.5 pr-2 text-muted-foreground" colSpan={9}>
                          無法取得資料：{h.error}
                        </td>
                      ) : (
                        <>
                          <td className="py-1.5 pr-2 text-right tabular-nums">{h.close?.toFixed(2)}</td>
                          <td className="py-1.5 pr-2 text-right tabular-nums">
                            {h.market_value?.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                          </td>
                          <td className="py-1.5 pr-2 text-right tabular-nums">{h.weight_pct ?? "—"}</td>
                          <td className="py-1.5 pr-2 text-right">
                            <PlCell value={h.unrealized_pl ?? 0} />
                          </td>
                          <td className="py-1.5 pr-2 text-right tabular-nums">
                            {h.unrealized_pl_pct != null ? `${h.unrealized_pl_pct > 0 ? "+" : ""}${h.unrealized_pl_pct}%` : "—"}
                          </td>
                          <td className="py-1.5 pr-2 text-right">
                            <ScoreCell score={h.technical_score ?? 0} />
                          </td>
                          <td className="py-1.5 pr-2 text-right tabular-nums">
                            {h.fundamental_rating != null ? `${h.fundamental_rating.toFixed(1)}` : "—"}
                          </td>
                          <td className="py-1.5 pr-2 text-center">
                            {h.quality_badge ? (
                              <Badge className={QUALITY_BADGE_COLOR[h.quality_badge]}>{h.quality_badge}</Badge>
                            ) : (
                              <span className="text-muted-foreground">—</span>
                            )}
                          </td>
                          <td className="py-1.5 pr-2">
                            {h.suggestion ? (
                              <Badge className={SUGGESTION_BADGE[h.suggestion]}>{h.suggestion_label}</Badge>
                            ) : (
                              <span className="text-muted-foreground">—</span>
                            )}
                          </td>
                        </>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

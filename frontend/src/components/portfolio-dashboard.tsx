"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { PortfolioValueChart } from "@/components/portfolio-value-chart";
import { SortableTh } from "@/components/sortable-th";
import { InfoTip } from "@/components/info-tip";
import { useSortableData } from "@/lib/use-sortable-data";
import { SUGGESTION_BADGE, type Suggestion } from "@/lib/suggestion-badge";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// 3 個固定成員——這個專案是單一使用者的個人工具，不需要一般化成任意多人的帳號系統，
// 固定清單比再蓋一套「新增/刪除成員」的管理介面務實。
const OWNERS = ["我", "太太", "女兒"] as const;
type Owner = (typeof OWNERS)[number];

// The dashboard takes minutes to compute (a live technical+fundamental pass over every holding),
// so re-running it every time this page remounts — e.g. navigating to a stock's detail page and
// back — would be wasteful. Cache the last result in sessionStorage, **per owner** (switching
// the 我/太太/女兒 tab must not show another member's stale cached numbers); only "重新整理"
// (or the very first visit this session for that owner) triggers a real recompute.
const CACHE_KEY_PREFIX = "portfolio-dashboard-cache:";

type CachedDashboard = { holdings: Holding[]; cachedAt: string };

function readCache(owner: Owner): CachedDashboard | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(CACHE_KEY_PREFIX + owner);
    return raw ? (JSON.parse(raw) as CachedDashboard) : null;
  } catch {
    return null;
  }
}

function writeCache(owner: Owner, holdings: Holding[]): string {
  const cachedAt = new Date().toISOString();
  try {
    window.sessionStorage.setItem(CACHE_KEY_PREFIX + owner, JSON.stringify({ holdings, cachedAt }));
  } catch {
    // sessionStorage unavailable — just skip caching, next mount will recompute
  }
  return cachedAt;
}

type OwnerSummary = {
  owner: string;
  market_value: number;
  unrealized_pl: number;
  unrealized_pl_pct: number | null;
  estimated_dividend_total: number;
  estimated_net_proceeds: number;
  estimated_net_pl: number;
  holding_count: number;
  error_count: number;
};

type PortfolioSummary = { owners: OwnerSummary[]; total: OwnerSummary & { owner?: string } };

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
  estimated_net_proceeds?: number;
  estimated_net_pl?: number;
  dividend_yield_pct?: number | null;
  estimated_dividend_per_share?: number | null;
  estimated_dividend_total?: number | null;
  technical_score?: number;
  technical_verdict_label?: string;
  grade?: "A" | "B" | "C" | "D";
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

// 訊號品質分級（A訊號廣、可信 ~ D訊號窄或已被覆蓋率封頂為中性）——不是方向性判斷，
// 刻意不沿用紅漲/綠跌配色。
const GRADE_BADGE_COLOR: Record<"A" | "B" | "C" | "D", string> = {
  A: "bg-green-600 text-white",
  B: "bg-blue-600 text-white",
  C: "bg-amber-500 text-white",
  D: "bg-zinc-500 text-white",
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

function getHoldingSortValue(h: Holding, key: string): string | number | null | undefined {
  switch (key) {
    case "name":
      return `${h.symbol} ${h.name}`;
    case "shares":
      return h.shares;
    case "cost_basis":
      return h.cost_basis;
    case "close":
      return h.close;
    case "market_value":
      return h.market_value;
    case "weight_pct":
      return h.weight_pct;
    case "unrealized_pl":
      return h.unrealized_pl;
    case "unrealized_pl_pct":
      return h.unrealized_pl_pct;
    case "estimated_net_proceeds":
      return h.estimated_net_proceeds;
    case "estimated_net_pl":
      return h.estimated_net_pl;
    case "dividend_yield_pct":
      return h.dividend_yield_pct;
    case "estimated_dividend_total":
      return h.estimated_dividend_total;
    case "technical_score":
      return h.technical_score;
    case "grade":
      return h.grade;
    case "fundamental_rating":
      return h.fundamental_rating;
    case "quality_badge":
      return h.quality_badge;
    case "suggestion":
      return h.suggestion_label;
    default:
      return null;
  }
}

export function PortfolioDashboard() {
  const [selectedOwner, setSelectedOwner] = useState<Owner>("我");
  const [showValueChart, setShowValueChart] = useState(false);

  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [summaryStatus, setSummaryStatus] = useState<"loading" | "done" | "error">("loading");
  const [summaryError, setSummaryError] = useState<string | null>(null);

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

  async function fetchSummary() {
    setSummaryStatus("loading");
    setSummaryError(null);
    try {
      const res = await fetch(`${API_URL}/api/v1/portfolio/summary`);
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      const body: PortfolioSummary = await res.json();
      setSummary(body);
      setSummaryStatus("done");
    } catch (err) {
      setSummaryError(err instanceof Error ? err.message : String(err));
      setSummaryStatus("error");
    }
  }

  async function fetchDashboard(owner: Owner) {
    setDashboardStatus("loading");
    setDashboardError(null);
    try {
      const res = await fetch(`${API_URL}/api/v1/portfolio?owner=${encodeURIComponent(owner)}`);
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      const body: { holdings: Holding[] } = await res.json();
      setHoldings(body.holdings);
      setCachedAt(writeCache(owner, body.holdings));
      setDashboardStatus("done");
    } catch (err) {
      setDashboardError(err instanceof Error ? err.message : String(err));
      setDashboardStatus("error");
    }
  }

  useEffect(() => {
    fetchSummary();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const cached = readCache(selectedOwner);
    if (cached) {
      setHoldings(cached.holdings);
      setCachedAt(cached.cachedAt);
      setDashboardStatus("done");
    } else {
      fetchDashboard(selectedOwner);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedOwner]);

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

  const { sortedRows: sortedHoldings, sortKey, sortDir, requestSort } = useSortableData(
    holdings,
    getHoldingSortValue
  );

  const validHoldings = holdings.filter((h) => !h.error && h.market_value != null && h.unrealized_pl != null);
  const totalMarketValue = validHoldings.reduce((sum, h) => sum + (h.market_value ?? 0), 0);
  const totalUnrealizedPl = validHoldings.reduce((sum, h) => sum + (h.unrealized_pl ?? 0), 0);
  const totalCostBasis = totalMarketValue - totalUnrealizedPl;
  const totalUnrealizedPlPct = totalCostBasis !== 0 ? (totalUnrealizedPl / totalCostBasis) * 100 : null;
  const totalEstimatedDividend = validHoldings.reduce((sum, h) => sum + (h.estimated_dividend_total ?? 0), 0);
  const totalEstimatedNetPl = validHoldings.reduce((sum, h) => sum + (h.estimated_net_pl ?? 0), 0);

  async function confirmImport() {
    setImportStatus("importing");
    try {
      const res = await fetch(`${API_URL}/api/v1/portfolio/import`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ owner: selectedOwner, rows: previewRows }),
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
      await Promise.all([fetchDashboard(selectedOwner), fetchSummary()]);
    } catch (err) {
      setParseError(err instanceof Error ? err.message : String(err));
      setImportStatus("error");
    }
  }

  const summaryByOwner = new Map((summary?.owners ?? []).map((o) => [o.owner, o]));

  return (
    <div className="w-full max-w-5xl space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">持股總覽</CardTitle>
          <Button variant="secondary" size="sm" onClick={() => setShowValueChart((v) => !v)}>
            {showValueChart ? "收起市值歷史" : "查看市值歷史"}
          </Button>
        </CardHeader>
        <CardContent>
          {summaryStatus === "loading" && <p className="text-sm text-muted-foreground">讀取中…</p>}
          {summaryStatus === "error" && <p className="text-sm text-muted-foreground">讀取失敗：{summaryError}</p>}
          {summaryStatus === "done" && summary && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-muted-foreground">
                  <tr className="text-left">
                    <th className="py-1 pr-2">成員</th>
                    <th className="py-1 pr-2 text-right">市值</th>
                    <th className="py-1 pr-2 text-right">損益</th>
                    <th className="py-1 pr-2 text-right">損益%</th>
                    <th className="py-1 pr-2 text-right">預估變現損益</th>
                    <th className="py-1 pr-2 text-right">預估股利</th>
                  </tr>
                </thead>
                <tbody>
                  {OWNERS.map((owner) => {
                    const s = summaryByOwner.get(owner);
                    return (
                      <tr
                        key={owner}
                        className={`cursor-pointer border-t align-top hover:bg-muted/50 ${
                          selectedOwner === owner ? "bg-muted/50" : ""
                        }`}
                        onClick={() => setSelectedOwner(owner)}
                      >
                        <td className="py-1.5 pr-2 font-medium">{owner}</td>
                        {s && s.holding_count > 0 ? (
                          <>
                            <td className="py-1.5 pr-2 text-right tabular-nums">
                              {s.market_value.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                            </td>
                            <td className="py-1.5 pr-2 text-right">
                              <PlCell value={s.unrealized_pl} />
                            </td>
                            <td className="py-1.5 pr-2 text-right tabular-nums">
                              {s.unrealized_pl_pct != null ? `${s.unrealized_pl_pct > 0 ? "+" : ""}${s.unrealized_pl_pct}%` : "—"}
                            </td>
                            <td className="py-1.5 pr-2 text-right">
                              <PlCell value={s.estimated_net_pl} />
                            </td>
                            <td className="py-1.5 pr-2 text-right tabular-nums">
                              {s.estimated_dividend_total.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                            </td>
                          </>
                        ) : (
                          <td className="py-1.5 pr-2 text-muted-foreground" colSpan={5}>
                            尚無庫存資料
                          </td>
                        )}
                      </tr>
                    );
                  })}
                  <tr className="border-t-2 font-medium">
                    <td className="py-1.5 pr-2">總計</td>
                    <td className="py-1.5 pr-2 text-right tabular-nums">
                      {summary.total.market_value.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </td>
                    <td className="py-1.5 pr-2 text-right">
                      <PlCell value={summary.total.unrealized_pl} />
                    </td>
                    <td className="py-1.5 pr-2 text-right tabular-nums">
                      {summary.total.unrealized_pl_pct != null
                        ? `${summary.total.unrealized_pl_pct > 0 ? "+" : ""}${summary.total.unrealized_pl_pct}%`
                        : "—"}
                    </td>
                    <td className="py-1.5 pr-2 text-right">
                      <PlCell value={summary.total.estimated_net_pl} />
                    </td>
                    <td className="py-1.5 pr-2 text-right tabular-nums">
                      {summary.total.estimated_dividend_total.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </td>
                  </tr>
                </tbody>
              </table>
              <p className="mt-2 text-xs text-muted-foreground">
                預估變現損益＝市值扣掉估計的賣出手續費與證交稅後，再減成本——用公版費率估算（手續費
                0.1425%，股票證交稅 0.3%／ETF 0.1%／債券型 ETF 免稅），跟您實際的券商折扣費率會有小幅落差。
              </p>
            </div>
          )}
        </CardContent>
        {showValueChart && (
          <CardContent className="border-t pt-4">
            <PortfolioValueChart />
          </CardContent>
        )}
      </Card>

      <div className="flex gap-2">
        {OWNERS.map((owner) => (
          <Button
            key={owner}
            variant={selectedOwner === owner ? "default" : "secondary"}
            size="sm"
            onClick={() => setSelectedOwner(owner)}
          >
            {owner}
          </Button>
        ))}
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">持股庫存匯入（{selectedOwner}）</CardTitle>
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
          <CardTitle className="text-base">持股盤點與建議（{selectedOwner}）</CardTitle>
          <div className="flex items-center gap-2">
            {cachedAt && dashboardStatus === "done" && (
              <span className="text-xs text-muted-foreground">
                上次更新：{new Date(cachedAt).toLocaleTimeString()}
              </span>
            )}
            <Button onClick={() => fetchDashboard(selectedOwner)} disabled={dashboardStatus === "loading"} variant="secondary">
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
                <div>
                  <span className="text-muted-foreground">預估變現損益　</span>
                  <PlCell value={totalEstimatedNetPl} />
                </div>
                <div>
                  <span className="text-muted-foreground">預估總股利　</span>
                  <span className="font-medium tabular-nums">
                    {totalEstimatedDividend.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                  </span>
                </div>
              </div>
              <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-muted-foreground">
                  <tr className="text-left">
                    <SortableTh sortKey="name" label="股票" align="left" activeKey={sortKey} dir={sortDir} onSort={requestSort} />
                    <SortableTh sortKey="shares" label="股數" activeKey={sortKey} dir={sortDir} onSort={requestSort} />
                    <SortableTh sortKey="cost_basis" label="成本均價" activeKey={sortKey} dir={sortDir} onSort={requestSort} />
                    <SortableTh sortKey="close" label="現價" activeKey={sortKey} dir={sortDir} onSort={requestSort} />
                    <SortableTh sortKey="market_value" label="市值" activeKey={sortKey} dir={sortDir} onSort={requestSort} />
                    <SortableTh sortKey="weight_pct" label="權重%" activeKey={sortKey} dir={sortDir} onSort={requestSort} />
                    <SortableTh sortKey="unrealized_pl" label="損益" activeKey={sortKey} dir={sortDir} onSort={requestSort} />
                    <SortableTh sortKey="unrealized_pl_pct" label="損益%" activeKey={sortKey} dir={sortDir} onSort={requestSort} />
                    <SortableTh sortKey="estimated_net_pl" label="預估變現損益" activeKey={sortKey} dir={sortDir} onSort={requestSort} />
                    <SortableTh sortKey="dividend_yield_pct" label="殖利率" activeKey={sortKey} dir={sortDir} onSort={requestSort} />
                    <SortableTh sortKey="estimated_dividend_total" label="預估股利" activeKey={sortKey} dir={sortDir} onSort={requestSort} />
                    <SortableTh
                      sortKey="technical_score"
                      label={
                        <>
                          技術分數
                          <InfoTip title="技術分數">
                            <p>
                              綜合「八層分析」（葛蘭碧、KD、MACD、乖離率、RSI、成交量、融資融券、法人買賣、波浪）算出的技術面總分，範圍
                              -100～+100。
                            </p>
                            <p>正值（紅）代表偏多訊號較強，負值（綠）代表偏空訊號較強；數字大小反映訊號強度，不代表預期漲跌幅度。</p>
                          </InfoTip>
                        </>
                      }
                      activeKey={sortKey}
                      dir={sortDir}
                      onSort={requestSort}
                    />
                    <SortableTh
                      sortKey="grade"
                      label={
                        <>
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
                        </>
                      }
                      align="center"
                      activeKey={sortKey}
                      dir={sortDir}
                      onSort={requestSort}
                    />
                    <SortableTh
                      sortKey="fundamental_rating"
                      label={
                        <>
                          基本面★
                          <InfoTip title="基本面★">
                            <p>
                              依據財報體質檢查清單（獲利能力、成長性、股東回報等指標）算出的 1.0～5.0
                              顆星評分：1 + 達標項目比例 × 4。
                            </p>
                            <p>星數越高代表通過越多項基本面檢核，而非「買進評等」。</p>
                          </InfoTip>
                        </>
                      }
                      activeKey={sortKey}
                      dir={sortDir}
                      onSort={requestSort}
                    />
                    <SortableTh sortKey="quality_badge" label="財報狗清單" align="center" activeKey={sortKey} dir={sortDir} onSort={requestSort} />
                    <SortableTh sortKey="suggestion" label="建議" align="left" activeKey={sortKey} dir={sortDir} onSort={requestSort} />
                  </tr>
                </thead>
                <tbody>
                  {sortedHoldings.map((h) => (
                    <tr key={h.symbol} className="border-t align-top">
                      <td className="py-1.5 pr-2">
                        <Link href={`/analyze/${h.symbol}`} className="font-medium hover:underline">
                          {h.symbol} {h.name}
                        </Link>
                      </td>
                      <td className="py-1.5 pr-2 text-right tabular-nums">{h.shares.toLocaleString()}</td>
                      <td className="py-1.5 pr-2 text-right tabular-nums">{h.cost_basis.toFixed(2)}</td>
                      {h.error ? (
                        <td className="py-1.5 pr-2 text-muted-foreground" colSpan={13}>
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
                            {h.estimated_net_pl != null ? <PlCell value={h.estimated_net_pl} /> : "—"}
                          </td>
                          <td className="py-1.5 pr-2 text-right tabular-nums">
                            {h.dividend_yield_pct != null ? `${h.dividend_yield_pct.toFixed(2)}%` : "—"}
                          </td>
                          <td className="py-1.5 pr-2 text-right tabular-nums">
                            {h.estimated_dividend_total != null
                              ? h.estimated_dividend_total.toLocaleString(undefined, { maximumFractionDigits: 0 })
                              : "—"}
                          </td>
                          <td className="py-1.5 pr-2 text-right">
                            <ScoreCell score={h.technical_score ?? 0} />
                          </td>
                          <td className="py-1.5 pr-2 text-center">
                            {h.grade ? (
                              <Badge className={GRADE_BADGE_COLOR[h.grade]}>{h.grade}</Badge>
                            ) : (
                              <span className="text-muted-foreground">—</span>
                            )}
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

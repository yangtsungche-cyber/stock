"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type ChecklistItem = {
  key: string;
  label: string;
  value: number | null;
  passed: boolean | null;
};

type Fundamentals = {
  has_data: boolean;
  as_of: string | null;
  profile: {
    total_assets: number | null;
    equity: number | null;
    roe: number | null;
    roa: number | null;
    debt_ratio: number | null;
    current_ratio: number | null;
  };
  profitability: {
    eps: number | null;
    eps_ttm: number | null;
    eps_growth_pct: number | null;
    gross_margin_pct: number | null;
    gross_margin_yoy_pp: number | null;
  };
  growth: {
    revenue_cagr_3y_pct: number | null;
    free_cash_flow: number | null;
  };
  shareholder_return: {
    dividend_yield_pct: number | null;
    pe_ratio: number | null;
    pb_ratio: number | null;
    consecutive_dividend_years: number;
  };
  checklist: ChecklistItem[];
  rating: number | null;
  rating_label: string;
  summary: string;
};

function useJson<T>(path: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    setError(null);
    const controller = new AbortController();
    fetch(`${API_URL}${path}`, { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then(setData)
      .catch((err: Error) => {
        if (err.name !== "AbortError") setError(err.message);
      });
    return () => controller.abort();
  }, [path]);

  return { data, error };
}

function fmtPct(n: number | null, digits = 2) {
  if (n === null) return "—";
  return `${n > 0 ? "+" : ""}${n.toFixed(digits)}%`;
}

function fmtPP(n: number | null) {
  if (n === null) return "—";
  return `${n > 0 ? "+" : ""}${n.toFixed(2)}pp`;
}

function fmtNum(n: number | null) {
  if (n === null) return "—";
  return n.toLocaleString("zh-Hant", { maximumFractionDigits: 0 });
}

function Stars({ rating }: { rating: number }) {
  const full = Math.round(rating);
  return (
    <span className="text-lg text-amber-500" aria-label={`${rating.toFixed(1)} / 5`}>
      {"★".repeat(full)}
      <span className="text-muted-foreground">{"★".repeat(5 - full)}</span>
    </span>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-sm font-medium">{value}</p>
    </div>
  );
}

export function FundamentalsPanel({ symbol }: { symbol: string }) {
  const { data, error } = useJson<Fundamentals>(`/api/v1/stocks/${encodeURIComponent(symbol)}/fundamentals`);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">基本面分析：AI基本面評等</CardTitle>
      </CardHeader>
      <CardContent>
        {error && <p className="text-sm text-muted-foreground">無法取得資料：{error}</p>}
        {!data && !error && <Skeleton className="h-64 w-full" />}
        {data && !data.has_data && <p className="text-sm text-muted-foreground">{data.summary}</p>}

        {data && data.has_data && (
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              {data.rating !== null && <Stars rating={data.rating} />}
              <span className="text-sm font-medium">{data.rating_label}</span>
            </div>
            <p className="text-sm text-muted-foreground">{data.summary}</p>

            <div>
              <p className="mb-2 text-sm font-medium">公司體質</p>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <Metric label="ROE" value={fmtPct(data.profile.roe)} />
                <Metric label="ROA" value={fmtPct(data.profile.roa)} />
                <Metric label="負債比" value={fmtPct(data.profile.debt_ratio)} />
                <Metric label="流動比率" value={fmtPct(data.profile.current_ratio)} />
                <Metric label="資產總額" value={fmtNum(data.profile.total_assets)} />
                <Metric label="權益總額" value={fmtNum(data.profile.equity)} />
              </div>
            </div>

            <div>
              <p className="mb-2 text-sm font-medium">獲利能力</p>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <Metric label="最新單季EPS" value={data.profitability.eps?.toFixed(2) ?? "—"} />
                <Metric label="近四季EPS(TTM)" value={data.profitability.eps_ttm?.toFixed(2) ?? "—"} />
                <Metric label="EPS成長率(近四季)" value={fmtPct(data.profitability.eps_growth_pct)} />
                <Metric label="毛利率" value={fmtPct(data.profitability.gross_margin_pct)} />
                <Metric label="毛利率年增" value={fmtPP(data.profitability.gross_margin_yoy_pp)} />
              </div>
            </div>

            <div>
              <p className="mb-2 text-sm font-medium">成長能力</p>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <Metric label="營收CAGR(近三年)" value={fmtPct(data.growth.revenue_cagr_3y_pct)} />
                <Metric label="自由現金流" value={fmtNum(data.growth.free_cash_flow)} />
              </div>
            </div>

            <div>
              <p className="mb-2 text-sm font-medium">股東回報</p>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <Metric label="殖利率" value={fmtPct(data.shareholder_return.dividend_yield_pct)} />
                <Metric label="本益比" value={data.shareholder_return.pe_ratio?.toFixed(2) ?? "—"} />
                <Metric label="股價淨值比" value={data.shareholder_return.pb_ratio?.toFixed(2) ?? "—"} />
                <Metric label="連續配息年數" value={`${data.shareholder_return.consecutive_dividend_years} 年`} />
              </div>
            </div>

            <div>
              <p className="mb-2 text-sm font-medium">篩選條件檢核</p>
              <ul className="space-y-1 text-sm">
                {data.checklist.map((item) => (
                  <li key={item.key} className="flex items-center gap-2">
                    <span
                      className={
                        item.passed === null
                          ? "text-muted-foreground"
                          : item.passed
                            ? "text-red-600"
                            : "text-emerald-600"
                      }
                    >
                      {item.passed === null ? "—" : item.passed ? "✓" : "✕"}
                    </span>
                    <span className="text-muted-foreground">{item.label}</span>
                  </li>
                ))}
              </ul>
            </div>

            <p className="text-xs text-muted-foreground">
              資料來源：FinMind（財報／資產負債／現金流／股利，截至 {data.as_of}）＋ 證交所／櫃買中心（本益比／殖利率，當日快照）。
              「本益比低於產業平均」需全市場資料，留待後續全市場篩選功能提供。
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

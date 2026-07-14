"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Stance = "buy" | "sell" | "neutral";

type ReferenceLevels = { close: number | null; support: number | null; resistance: number | null };
type EntryZone = { low: number; high: number };
type PositionSizing = { tier: "high" | "medium" | "low" | "none"; label: string; note: string };

type PlaybookResult = {
  date: string;
  score: number;
  verdict: string;
  verdict_label: string;
  stance: Stance;
  stance_label: string;
  action_note: string;
  reference_levels: ReferenceLevels;
  entry_zone: EntryZone | null;
  stop_loss: number | null;
  stop_loss_note: string | null;
  target: number | null;
  risk_reward_ratio: number | null;
  position_sizing: PositionSizing;
  invalidation: string[];
  disclaimer: string;
};

const STANCE_STYLE: Record<Stance, { dot: string; badge: string }> = {
  buy: { dot: "bg-red-600", badge: "bg-red-600 hover:bg-red-600" },
  neutral: { dot: "bg-amber-500", badge: "bg-amber-500 hover:bg-amber-500" },
  sell: { dot: "bg-emerald-600", badge: "bg-emerald-600 hover:bg-emerald-600" },
};

// Position-sizing badge follows the stance's buy/sell color (matching the
// verdict badge above it), not an independent urgency scale — otherwise a
// "reduce aggressively" (sell) recommendation would render in the same red
// this app uses everywhere else to mean bullish/buy.
const SIZING_STYLE: Record<Stance, string> = {
  buy: "bg-red-600 hover:bg-red-600",
  sell: "bg-emerald-600 hover:bg-emerald-600",
  neutral: "bg-amber-500 hover:bg-amber-500",
};

function fmtPrice(n: number | null) {
  return n === null ? "—" : n.toFixed(2);
}

export function PlaybookPanel({ symbol }: { symbol: string }) {
  const [data, setData] = useState<PlaybookResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    setError(null);
    const controller = new AbortController();
    fetch(`${API_URL}/api/v1/stocks/${encodeURIComponent(symbol)}/playbook`, {
      signal: controller.signal,
    })
      .then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail ?? `HTTP ${res.status}`);
        }
        return res.json();
      })
      .then(setData)
      .catch((err: Error) => {
        if (err.name !== "AbortError") setError(err.message);
      });
    return () => controller.abort();
  }, [symbol]);

  if (error) {
    return (
      <Card>
        <CardContent className="py-6 text-sm text-muted-foreground">無法取得資料：{error}</CardContent>
      </Card>
    );
  }

  if (!data) {
    return (
      <div className="space-y-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Investment Playbook</CardTitle>
          </CardHeader>
          <CardContent>
            <Skeleton className="h-24 w-full" />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">進出場價位</CardTitle>
          </CardHeader>
          <CardContent>
            <Skeleton className="h-32 w-full" />
          </CardContent>
        </Card>
      </div>
    );
  }

  const style = STANCE_STYLE[data.stance];
  const levels = data.reference_levels;

  return (
    <div className="space-y-3">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Investment Playbook</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex items-center gap-3">
            <span className={`h-3 w-3 shrink-0 rounded-full ${style.dot}`} />
            <Badge className={style.badge}>{data.stance_label}</Badge>
            <span className="text-sm text-muted-foreground">
              綜合分數 {data.score > 0 ? "+" : ""}
              {data.score}（{data.verdict_label}）
            </span>
          </div>
          <p className="text-sm text-muted-foreground">{data.action_note}</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">進出場價位</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-muted-foreground">
            <span>現價：{fmtPrice(levels.close)}</span>
            <span>支撐：{fmtPrice(levels.support)}</span>
            <span>壓力：{fmtPrice(levels.resistance)}</span>
          </div>
          <ul className="space-y-1.5 text-sm">
            {data.entry_zone && (
              <li>
                <span className="font-medium">進場區間：</span>
                {fmtPrice(data.entry_zone.low)} ～ {fmtPrice(data.entry_zone.high)}
              </li>
            )}
            {data.stop_loss !== null && (
              <li>
                <span className="font-medium">{data.stance === "buy" ? "停損價：" : "防守／減碼價："}</span>
                {fmtPrice(data.stop_loss)}
                {data.stop_loss_note && <span className="text-muted-foreground">（{data.stop_loss_note}）</span>}
              </li>
            )}
            {data.target !== null && (
              <li>
                <span className="font-medium">{data.stance === "buy" ? "目標價：" : "逢高調節價："}</span>
                {fmtPrice(data.target)}
              </li>
            )}
            {data.risk_reward_ratio !== null && (
              <li>
                <span className="font-medium">風險報酬比：</span>
                {data.risk_reward_ratio.toFixed(2)}
              </li>
            )}
            {!data.entry_zone && data.stop_loss === null && data.target === null && (
              <li className="text-muted-foreground">目前無明確進出場建議，僅列出支撐／壓力供觀察。</li>
            )}
          </ul>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">部位建議</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <Badge className={SIZING_STYLE[data.stance]}>{data.position_sizing.label}</Badge>
          <p className="text-sm text-muted-foreground">{data.position_sizing.note}</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">情境失效條件</CardTitle>
        </CardHeader>
        <CardContent>
          {data.invalidation.length === 0 ? (
            <p className="text-sm text-muted-foreground">目前無特別條件。</p>
          ) : (
            <ul className="list-disc space-y-1.5 pl-5 text-sm">
              {data.invalidation.map((cond) => (
                <li key={cond}>{cond}</li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="py-4 text-xs text-muted-foreground">{data.disclaimer}</CardContent>
      </Card>
    </div>
  );
}

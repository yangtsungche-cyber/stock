"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Verdict = "strong_buy" | "buy" | "neutral" | "sell" | "strong_sell";

type Signal = {
  code: string;
  side: "buy" | "sell";
  label: string;
  confidence: number;
  reason: string;
  layer: string;
  contribution: number;
};

type LabeledSignal = Signal & { layer_label?: string };

type LayerStatus = "fired" | "neutral" | "no_data";

type LayerBreakdown = {
  layer: string;
  label: string;
  weight: number;
  signal_count: number;
  score: number;
  status: LayerStatus;
};

type Coverage = {
  layers_total: number;
  layers_with_data: number;
  layers_fired: number;
  coverage_pct: number;
  no_data_layers: string[];
};

type Grade = "A" | "B" | "C" | "D";

type DecisionResult = {
  date: string;
  score: number;
  verdict: Verdict;
  verdict_label: string;
  grade: Grade;
  raw_verdict: Verdict;
  verdict_capped: boolean;
  trend_context: { ma_alignment: string; note: string };
  coverage: Coverage;
  layer_breakdown: LayerBreakdown[];
  signals: Signal[];
};

const VERDICT_STYLE: Record<Verdict, { dot: string; badge: string }> = {
  strong_buy: { dot: "bg-red-600", badge: "bg-red-600 hover:bg-red-600" },
  buy: { dot: "bg-red-400", badge: "bg-red-500 hover:bg-red-500" },
  neutral: { dot: "bg-amber-500", badge: "bg-amber-500 hover:bg-amber-500" },
  sell: { dot: "bg-emerald-400", badge: "bg-emerald-500 hover:bg-emerald-500" },
  strong_sell: { dot: "bg-emerald-600", badge: "bg-emerald-600 hover:bg-emerald-600" },
};

// 訊號品質分級不是方向性訊號（不是「看多/看空」），是「這個判斷的訊號基礎廣不廣」，所以
// 刻意不沿用紅漲/綠跌配色——用另一套色階：A（訊號廣、可信）到 D（訊號窄或中性/被封頂）。
const GRADE_STYLE: Record<Grade, string> = {
  A: "bg-green-600 text-white",
  B: "bg-blue-600 text-white",
  C: "bg-amber-500 text-white",
  D: "bg-zinc-500 text-white",
};

const VERDICT_LABEL: Record<Verdict, string> = {
  strong_buy: "強烈偏多",
  buy: "偏多",
  neutral: "中性",
  sell: "偏空",
  strong_sell: "強烈偏空",
};

const MA_ALIGNMENT_LABEL: Record<string, string> = {
  bullish: "多頭排列",
  bearish: "空頭排列",
  mixed: "交錯排列",
  unknown: "資料不足",
};

function ScoreBar({ score }: { score: number }) {
  const pct = Math.min(100, Math.abs(score));
  const barColor = score >= 0 ? "bg-red-500" : "bg-emerald-500";
  return (
    <div className="flex h-2 w-full overflow-hidden rounded-full bg-muted">
      <div className="flex h-full w-1/2 flex-row-reverse">
        {score < 0 && <div className={`h-full ${barColor}`} style={{ width: `${pct}%` }} />}
      </div>
      <div className="flex h-full w-1/2">
        {score > 0 && <div className={`h-full ${barColor}`} style={{ width: `${pct}%` }} />}
      </div>
    </div>
  );
}

function CoverageMeter({ coverage }: { coverage: Coverage }) {
  const filled = Math.round(coverage.coverage_pct / 20);
  return (
    <div className="space-y-1 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-muted-foreground">訊號完整度</span>
        <span aria-hidden className="tracking-tight text-amber-500">
          {"★".repeat(filled)}
          <span className="text-muted-foreground">{"★".repeat(5 - filled)}</span>
        </span>
        <span className="tabular-nums">
          {coverage.layers_fired} / {coverage.layers_with_data} 層有訊號（涵蓋率 {coverage.coverage_pct}%）
        </span>
      </div>
      {coverage.no_data_layers.length > 0 && (
        <p className="text-muted-foreground">
          無資料，未納入評估：{coverage.no_data_layers.join("、")}
        </p>
      )}
    </div>
  );
}

function SignalBadges({ signals }: { signals: LabeledSignal[] }) {
  if (signals.length === 0) {
    return <p className="text-sm text-muted-foreground">目前無任何層級產生訊號。</p>;
  }
  return (
    <ul className="space-y-2">
      {signals.map((s) => (
        <li key={`${s.layer}-${s.code}`} className="flex items-start gap-2 text-sm">
          <Badge
            variant={s.side === "buy" ? "default" : "destructive"}
            className={s.side === "buy" ? "bg-red-600 hover:bg-red-600" : "bg-emerald-600 hover:bg-emerald-600"}
          >
            {s.code}
          </Badge>
          <span>
            <span className="font-medium">{s.label}</span>
            <span className="text-muted-foreground">
              （{s.layer_label ?? s.layer}・信心 {s.confidence}%・貢獻度 {s.contribution > 0 ? "+" : ""}
              {s.contribution}）— {s.reason}
            </span>
          </span>
        </li>
      ))}
    </ul>
  );
}

export function DecisionSummaryPanel({ symbol }: { symbol: string }) {
  const [data, setData] = useState<DecisionResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    setError(null);
    const controller = new AbortController();
    fetch(`${API_URL}/api/v1/stocks/${encodeURIComponent(symbol)}/decision`, {
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
            <CardTitle className="text-base">Adaptive Weighted Decision Engine</CardTitle>
          </CardHeader>
          <CardContent>
            <Skeleton className="h-24 w-full" />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">各層貢獻分解</CardTitle>
          </CardHeader>
          <CardContent>
            <Skeleton className="h-40 w-full" />
          </CardContent>
        </Card>
      </div>
    );
  }

  const style = VERDICT_STYLE[data.verdict];
  const labeledSignals = data.signals.map((s) => ({
    ...s,
    layer_label: data.layer_breakdown.find((l) => l.layer === s.layer)?.label,
  }));

  return (
    <div className="space-y-3">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">決策摘要（Adaptive Weighted Decision Engine）</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center gap-3">
            <span className={`h-3 w-3 shrink-0 rounded-full ${style.dot}`} />
            <Badge className={style.badge}>{data.verdict_label}</Badge>
            <Badge className={GRADE_STYLE[data.grade]}>{data.grade} 級</Badge>
            <span className="text-2xl font-semibold tabular-nums">
              {data.score > 0 ? "+" : ""}
              {data.score}
            </span>
            <span className="text-sm text-muted-foreground">綜合分數（-100 偏空 ～ +100 偏多）</span>
          </div>
          {data.verdict_capped && (
            <p className="text-sm text-amber-600">
              訊號覆蓋率過低（{data.coverage.coverage_pct}%），原始判斷「{VERDICT_LABEL[data.raw_verdict]}」已封頂為中性，避免少數訊號拉高整體判斷。
            </p>
          )}
          <ScoreBar score={data.score} />
          <p className="text-sm text-muted-foreground">
            均線排列：{MA_ALIGNMENT_LABEL[data.trend_context.ma_alignment] ?? data.trend_context.ma_alignment}。
            {data.trend_context.note}。
          </p>
          <CoverageMeter coverage={data.coverage} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">各層貢獻分解</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-2">
            {data.layer_breakdown.map((l) =>
              l.status === "no_data" ? (
                <li key={l.layer} className="flex items-center gap-3 text-sm text-muted-foreground">
                  <span className="w-40 shrink-0">{l.label}</span>
                  <span className="flex-1">權重 {l.weight.toFixed(1)}・無資料，未納入評估</span>
                </li>
              ) : (
                <li key={l.layer} className="flex items-center gap-3 text-sm">
                  <span className="w-40 shrink-0">{l.label}</span>
                  <span className="w-28 shrink-0 text-muted-foreground">
                    權重 {l.weight.toFixed(1)}・{l.signal_count} 訊號
                  </span>
                  <span className="min-w-0 flex-1">
                    <ScoreBar score={l.score} />
                  </span>
                  <span className="w-16 shrink-0 text-right tabular-nums">
                    {l.score > 0 ? "+" : ""}
                    {l.score}
                  </span>
                </li>
              )
            )}
          </ul>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">訊號明細（依貢獻度排序）</CardTitle>
        </CardHeader>
        <CardContent>
          <SignalBadges signals={labeledSignals} />
        </CardContent>
      </Card>
    </div>
  );
}

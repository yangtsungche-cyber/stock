"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Signal = {
  code: string;
  side: "buy" | "sell";
  label: string;
  confidence: number;
  reason: string;
};

type LayersResult = {
  date: string;
  kd: { k: number | null; d: number | null; signals: Signal[] };
  macd: { macd: number | null; signal: number | null; histogram: number | null; signals: Signal[] };
  bias: { latest: Record<string, number | null>; signals: Signal[] };
  rsi: { rsi6: number | null; rsi14: number | null; signals: Signal[] };
  volume: { volume: number | null; volume_ma20: number | null; signals: Signal[] };
};

function SignalBadges({ signals }: { signals: Signal[] }) {
  if (signals.length === 0) {
    return <p className="text-sm text-muted-foreground">目前無訊號。</p>;
  }
  return (
    <ul className="space-y-2">
      {signals.map((s) => (
        <li key={s.code} className="flex items-start gap-2 text-sm">
          <Badge
            variant={s.side === "buy" ? "default" : "destructive"}
            className={s.side === "buy" ? "bg-red-600 hover:bg-red-600" : "bg-emerald-600 hover:bg-emerald-600"}
          >
            {s.code}
          </Badge>
          <span>
            <span className="font-medium">{s.label}</span>
            <span className="text-muted-foreground">（信心 {s.confidence}%）— {s.reason}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

function fmtNum(n: number | null, decimals = 2) {
  return n === null ? "—" : n.toFixed(decimals);
}

const BIAS_WINDOWS = ["5", "10", "20", "60", "120", "240"];

export function IndicatorLayersPanel({ symbol }: { symbol: string }) {
  const [data, setData] = useState<LayersResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    setError(null);
    const controller = new AbortController();
    fetch(`${API_URL}/api/v1/stocks/${encodeURIComponent(symbol)}/layers`, {
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
        {["第三層：KD", "第四層：MACD", "第五層：均線乖離率", "第六層：RSI", "第七層：成交量"].map((label) => (
          <Card key={label}>
            <CardHeader>
              <CardTitle className="text-base">{label}</CardTitle>
            </CardHeader>
            <CardContent>
              <Skeleton className="h-16 w-full" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">第三層：KD</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-muted-foreground">
            <span>K：{fmtNum(data.kd.k, 1)}</span>
            <span>D：{fmtNum(data.kd.d, 1)}</span>
          </div>
          <SignalBadges signals={data.kd.signals} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">第四層：MACD</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-muted-foreground">
            <span>MACD：{fmtNum(data.macd.macd, 3)}</span>
            <span>訊號線：{fmtNum(data.macd.signal, 3)}</span>
            <span>柱狀圖：{fmtNum(data.macd.histogram, 3)}</span>
          </div>
          <SignalBadges signals={data.macd.signals} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">第五層：均線乖離率</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-muted-foreground">
            {BIAS_WINDOWS.map((w) => (
              <span key={w}>
                {w}日：{fmtNum(data.bias.latest[w], 2)}%
              </span>
            ))}
          </div>
          <SignalBadges signals={data.bias.signals} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">第六層：RSI</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-muted-foreground">
            <span>RSI6：{fmtNum(data.rsi.rsi6, 1)}</span>
            <span>RSI14：{fmtNum(data.rsi.rsi14, 1)}</span>
          </div>
          <SignalBadges signals={data.rsi.signals} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">第七層：成交量</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-muted-foreground">
            <span>今日量：{data.volume.volume === null ? "—" : data.volume.volume.toLocaleString("zh-Hant")}</span>
            <span>20日均量：{data.volume.volume_ma20 === null ? "—" : data.volume.volume_ma20.toLocaleString("zh-Hant")}</span>
          </div>
          <SignalBadges signals={data.volume.signals} />
        </CardContent>
      </Card>
    </div>
  );
}

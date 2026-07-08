"use client";

import { useEffect, useState } from "react";
import { CandlestickChart } from "@/components/candlestick-chart";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Candle = { time: string; open: number; high: number; low: number; close: number };

const INTERVALS = [
  { value: "1d", label: "日K", period: "6mo" },
  { value: "1wk", label: "週K", period: "2y" },
  { value: "1mo", label: "月K", period: "10y" },
];

type FetchState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ok"; candles: Candle[]; yahooSymbol: string };

export function PriceChartPanel({ symbol }: { symbol: string }) {
  const [interval, setInterval] = useState("1d");
  const [state, setState] = useState<FetchState>({ status: "loading" });

  useEffect(() => {
    const config = INTERVALS.find((i) => i.value === interval) ?? INTERVALS[0];
    setState({ status: "loading" });

    const controller = new AbortController();
    fetch(
      `${API_URL}/api/v1/stocks/${encodeURIComponent(symbol)}/prices?interval=${config.value}&period=${config.period}`,
      { signal: controller.signal },
    )
      .then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail ?? `HTTP ${res.status}`);
        }
        return res.json();
      })
      .then((data) => {
        setState({ status: "ok", candles: data.candles, yahooSymbol: data.yahoo_symbol });
      })
      .catch((err: Error) => {
        if (err.name === "AbortError") return;
        setState({ status: "error", message: err.message });
      });

    return () => controller.abort();
  }, [symbol, interval]);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <Select value={interval} onValueChange={(value) => value && setInterval(value)}>
          <SelectTrigger className="w-28">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {INTERVALS.map((i) => (
              <SelectItem key={i.value} value={i.value}>
                {i.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {state.status === "ok" && (
          <span className="text-xs text-muted-foreground">
            資料來源：Yahoo Finance（{state.yahooSymbol}，還原權）
          </span>
        )}
      </div>

      {state.status === "loading" && <Skeleton className="h-[400px] w-full" />}

      {state.status === "error" && (
        <div className="flex h-[400px] w-full items-center justify-center rounded-md border border-dashed text-sm text-muted-foreground">
          無法取得資料：{state.message}
        </div>
      )}

      {state.status === "ok" && <CandlestickChart data={state.candles} />}
    </div>
  );
}

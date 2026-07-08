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

type GranvilleResult = {
  date: string;
  ma20_direction: string | null;
  ma60_direction: string | null;
  ma120_direction: string | null;
  ma_alignment: string;
  signals: Signal[];
};

const DIRECTION_LABEL: Record<string, string> = { up: "向上", down: "向下", flat: "走平" };
const ALIGNMENT_LABEL: Record<string, string> = {
  bullish: "多頭排列（20>60>120）",
  bearish: "空頭排列（20<60<120）",
  mixed: "不同步",
  unknown: "資料不足",
};

export function GranvillePanel({ symbol }: { symbol: string }) {
  const [data, setData] = useState<GranvilleResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    setError(null);
    const controller = new AbortController();
    fetch(`${API_URL}/api/v1/stocks/${encodeURIComponent(symbol)}/granville`, {
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

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">第一層：葛蘭碧八大法則</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {error && <p className="text-sm text-muted-foreground">無法取得資料：{error}</p>}
        {!data && !error && <Skeleton className="h-24 w-full" />}

        {data && (
          <>
            <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-muted-foreground">
              <span>20MA：{DIRECTION_LABEL[data.ma20_direction ?? ""] ?? "資料不足"}</span>
              <span>60MA：{DIRECTION_LABEL[data.ma60_direction ?? ""] ?? "資料不足"}</span>
              <span>120MA：{DIRECTION_LABEL[data.ma120_direction ?? ""] ?? "資料不足"}</span>
              <span>均線排列：{ALIGNMENT_LABEL[data.ma_alignment]}</span>
            </div>

            {data.signals.length === 0 ? (
              <p className="text-sm text-muted-foreground">今日無葛蘭碧買賣訊號。</p>
            ) : (
              <ul className="space-y-2">
                {data.signals.map((s) => (
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
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

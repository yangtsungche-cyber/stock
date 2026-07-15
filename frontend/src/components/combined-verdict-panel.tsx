"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Combined = {
  combined_label: string;
  technical_direction: "bullish" | "neutral" | "bearish";
  technical_verdict_label: string;
  fundamental_tier: "strong" | "moderate" | "weak" | null;
  fundamental_rating: number | null;
  fundamental_rating_label: string | null;
  has_fundamental_data: boolean;
};

// This app's convention: red = bullish, emerald = bearish, amber = neutral, everywhere.
const DIRECTION_COLOR: Record<string, string> = {
  bullish: "text-red-600",
  bearish: "text-emerald-600",
  neutral: "text-amber-600",
};

const TIER_LABEL: Record<string, string> = { strong: "強", moderate: "中等", weak: "弱" };

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

export function CombinedVerdictPanel({ symbol }: { symbol: string }) {
  const { data, error } = useJson<Combined>(`/api/v1/stocks/${encodeURIComponent(symbol)}/combined`);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">技術面 × 基本面綜合判斷</CardTitle>
      </CardHeader>
      <CardContent>
        {error && <p className="text-sm text-muted-foreground">無法取得資料：{error}</p>}
        {!data && !error && <Skeleton className="h-16 w-full" />}
        {data && (
          <div className="space-y-2">
            <p className={`text-lg font-semibold ${DIRECTION_COLOR[data.technical_direction]}`}>
              {data.combined_label}
            </p>
            <p className="text-sm text-muted-foreground">
              技術面：{data.technical_verdict_label}
              {data.has_fundamental_data && (
                <>
                  　｜　基本面：{TIER_LABEL[data.fundamental_tier!]}（{data.fundamental_rating_label}）
                </>
              )}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

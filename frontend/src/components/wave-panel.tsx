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

type Pivot = { date: string; price: number; type: "H" | "L" };
type WaveLabel = Pivot & { label: string };

type WaveResult = {
  date: string;
  threshold_pct: number;
  pivots: Pivot[];
  pattern: string;
  wave_labels: WaveLabel[];
  current_position: string;
  signals: Signal[];
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

export function WavePanel({ symbol }: { symbol: string }) {
  const [data, setData] = useState<WaveResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    setError(null);
    const controller = new AbortController();
    fetch(`${API_URL}/api/v1/stocks/${encodeURIComponent(symbol)}/waves`, {
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
        <CardHeader>
          <CardTitle className="text-base">第二層：波浪理論</CardTitle>
        </CardHeader>
        <CardContent className="py-6 text-sm text-muted-foreground">無法取得資料：{error}</CardContent>
      </Card>
    );
  }

  if (!data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">第二層：波浪理論</CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-16 w-full" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">第二層：波浪理論</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">{data.current_position}</p>

        {data.wave_labels.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {data.wave_labels.map((w, i) => (
              <Badge key={`${w.date}-${i}`} variant="outline" className="font-normal">
                {w.label}：{w.date} @ {w.price}
              </Badge>
            ))}
          </div>
        )}

        <SignalBadges signals={data.signals} />
      </CardContent>
    </Card>
  );
}

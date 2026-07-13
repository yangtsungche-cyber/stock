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

type Streak = { direction: "up" | "down" | "flat" | null; days: number };

type MarginRow = {
  date: string;
  margin_today_balance: number;
  margin_prev_balance: number;
  margin_change: number;
  margin_change_pct: number | null;
  short_today_balance: number;
  short_prev_balance: number;
  short_change: number;
  short_change_pct: number | null;
  short_margin_ratio: number | null;
};

type InstitutionalRow = {
  date: string;
  foreign_net: number;
  trust_net: number;
  dealer_net: number;
  total_net: number;
};

type Announcement = {
  date: string;
  subject: string;
};

function SignalList({ signals }: { signals: Signal[] }) {
  if (signals.length === 0) {
    return <p className="text-sm text-muted-foreground">目前無籌碼面訊號。</p>;
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

const STREAK_LABEL: Record<string, string> = { up: "增加", down: "減少", flat: "持平" };
const NET_STREAK_LABEL: Record<string, string> = { up: "買超", down: "賣超", flat: "持平" };

function fmtPct(n: number | null) {
  if (n === null) return "—";
  return `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;
}

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

function fmt(n: number) {
  return n.toLocaleString("zh-Hant");
}

export function MarginPanel({ symbol }: { symbol: string }) {
  const { data, error } = useJson<{ history: MarginRow[]; streak: Streak }>(
    `/api/v1/stocks/${encodeURIComponent(symbol)}/margin?days=20`,
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">融資融券明細（近 20 交易日）</CardTitle>
      </CardHeader>
      <CardContent>
        {error && <p className="text-sm text-muted-foreground">無法取得資料：{error}</p>}
        {!data && !error && <Skeleton className="h-40 w-full" />}
        {data && data.history.length === 0 && (
          <p className="text-sm text-muted-foreground">查無融資融券資料。</p>
        )}
        {data && data.history.length > 0 && (
          <>
            {data.streak.direction && data.streak.days >= 2 && (
              <p className="mb-2 text-sm text-muted-foreground">
                融資餘額已連續 {data.streak.days} 日{STREAK_LABEL[data.streak.direction]}。
              </p>
            )}
            <div className="max-h-64 overflow-auto">
              <table className="w-full text-sm">
                <thead className="text-muted-foreground">
                  <tr className="text-left">
                    <th className="py-1 pr-2">日期</th>
                    <th className="py-1 pr-2 text-right">融資餘額</th>
                    <th className="py-1 pr-2 text-right">變動%</th>
                    <th className="py-1 pr-2 text-right">融券餘額</th>
                    <th className="py-1 pr-2 text-right">變動%</th>
                    <th className="py-1 pr-2 text-right">券資比</th>
                  </tr>
                </thead>
                <tbody>
                  {data.history.map((row) => (
                    <tr key={row.date} className="border-t">
                      <td className="py-1 pr-2">{row.date}</td>
                      <td className="py-1 pr-2 text-right">{fmt(row.margin_today_balance)}</td>
                      <td className="py-1 pr-2 text-right">{fmtPct(row.margin_change_pct)}</td>
                      <td className="py-1 pr-2 text-right">{fmt(row.short_today_balance)}</td>
                      <td className="py-1 pr-2 text-right">{fmtPct(row.short_change_pct)}</td>
                      <td className="py-1 pr-2 text-right">
                        {row.short_margin_ratio === null ? "—" : `${row.short_margin_ratio.toFixed(2)}%`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
        <p className="mt-2 text-xs text-muted-foreground">
          資料來源：證交所 MI_MARGN。券資比 = 融券餘額 / 融資餘額。
        </p>
      </CardContent>
    </Card>
  );
}

type Rolling = Record<string, { foreign_net: number; trust_net: number; dealer_net: number; total_net: number }>;

export function InstitutionalPanel({ symbol }: { symbol: string }) {
  const { data, error } = useJson<{ history: InstitutionalRow[]; streak: Streak; rolling: Rolling }>(
    `/api/v1/stocks/${encodeURIComponent(symbol)}/institutional?days=20`,
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">三大法人買賣超（近 20 交易日）</CardTitle>
      </CardHeader>
      <CardContent>
        {error && <p className="text-sm text-muted-foreground">無法取得資料：{error}</p>}
        {!data && !error && <Skeleton className="h-40 w-full" />}
        {data && data.history.length === 0 && (
          <p className="text-sm text-muted-foreground">查無法人買賣超資料。</p>
        )}
        {data && data.history.length > 0 && (
          <>
            <div className="mb-2 space-y-1 text-sm text-muted-foreground">
              {data.streak.direction && data.streak.days >= 2 && (
                <p>
                  三大法人已連續 {data.streak.days} 日{NET_STREAK_LABEL[data.streak.direction]}。
                </p>
              )}
              {data.rolling["5d"] && (
                <p>
                  近 5 日合計{data.rolling["5d"].total_net >= 0 ? "買超" : "賣超"} {fmt(Math.abs(data.rolling["5d"].total_net))}
                  ，近 20 日合計{data.rolling["20d"].total_net >= 0 ? "買超" : "賣超"} {fmt(Math.abs(data.rolling["20d"].total_net))}。
                </p>
              )}
            </div>
            <div className="max-h-64 overflow-auto">
              <table className="w-full text-sm">
                <thead className="text-muted-foreground">
                  <tr className="text-left">
                    <th className="py-1 pr-2">日期</th>
                    <th className="py-1 pr-2 text-right">外資</th>
                    <th className="py-1 pr-2 text-right">投信</th>
                    <th className="py-1 pr-2 text-right">自營商</th>
                    <th className="py-1 pr-2 text-right">合計</th>
                  </tr>
                </thead>
                <tbody>
                  {data.history.map((row) => (
                    <tr key={row.date} className="border-t">
                      <td className="py-1 pr-2">{row.date}</td>
                      <td className="py-1 pr-2 text-right">{fmt(row.foreign_net)}</td>
                      <td className="py-1 pr-2 text-right">{fmt(row.trust_net)}</td>
                      <td className="py-1 pr-2 text-right">{fmt(row.dealer_net)}</td>
                      <td className="py-1 pr-2 text-right font-medium">{fmt(row.total_net)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
        <p className="mt-2 text-xs text-muted-foreground">資料來源：證交所 T86，單位：股。</p>
      </CardContent>
    </Card>
  );
}

export function ChipsSignalPanel({ symbol }: { symbol: string }) {
  const { data, error } = useJson<{ signals: Signal[] }>(
    `/api/v1/stocks/${encodeURIComponent(symbol)}/chips?days=20`,
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">第八層：籌碼面綜合訊號（融資融券 + 三大法人）</CardTitle>
      </CardHeader>
      <CardContent>
        {error && <p className="text-sm text-muted-foreground">無法取得資料：{error}</p>}
        {!data && !error && <Skeleton className="h-16 w-full" />}
        {data && <SignalList signals={data.signals} />}
      </CardContent>
    </Card>
  );
}

export function AnnouncementsPanel({ symbol }: { symbol: string }) {
  const { data, error } = useJson<{ announcements: Announcement[] }>(
    `/api/v1/stocks/${encodeURIComponent(symbol)}/announcements`,
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">重大公告（今日）</CardTitle>
      </CardHeader>
      <CardContent>
        {error && <p className="text-sm text-muted-foreground">無法取得資料：{error}</p>}
        {!data && !error && <Skeleton className="h-16 w-full" />}
        {data && data.announcements.length === 0 && (
          <p className="text-sm text-muted-foreground">今日無重大公告。</p>
        )}
        {data && data.announcements.length > 0 && (
          <ul className="space-y-2 text-sm">
            {data.announcements.map((a, i) => (
              <li key={i}>
                <span className="text-muted-foreground">{a.date}　</span>
                {a.subject}
              </li>
            ))}
          </ul>
        )}
        <p className="mt-2 text-xs text-muted-foreground">資料來源：證交所公開資訊 t187ap04_L。</p>
      </CardContent>
    </Card>
  );
}

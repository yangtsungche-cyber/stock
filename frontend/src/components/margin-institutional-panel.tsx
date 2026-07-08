"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type MarginRow = {
  date: string;
  margin_today_balance: number;
  margin_prev_balance: number;
  short_today_balance: number;
  short_prev_balance: number;
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
  const { data, error } = useJson<{ history: MarginRow[] }>(
    `/api/v1/stocks/${encodeURIComponent(symbol)}/margin?days=20`,
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">第八層：融資融券（近 20 交易日）</CardTitle>
      </CardHeader>
      <CardContent>
        {error && <p className="text-sm text-muted-foreground">無法取得資料：{error}</p>}
        {!data && !error && <Skeleton className="h-40 w-full" />}
        {data && data.history.length === 0 && (
          <p className="text-sm text-muted-foreground">查無融資融券資料。</p>
        )}
        {data && data.history.length > 0 && (
          <div className="max-h-64 overflow-auto">
            <table className="w-full text-sm">
              <thead className="text-muted-foreground">
                <tr className="text-left">
                  <th className="py-1 pr-2">日期</th>
                  <th className="py-1 pr-2 text-right">融資餘額</th>
                  <th className="py-1 pr-2 text-right">融券餘額</th>
                </tr>
              </thead>
              <tbody>
                {data.history.map((row) => (
                  <tr key={row.date} className="border-t">
                    <td className="py-1 pr-2">{row.date}</td>
                    <td className="py-1 pr-2 text-right">{fmt(row.margin_today_balance)}</td>
                    <td className="py-1 pr-2 text-right">{fmt(row.short_today_balance)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="mt-2 text-xs text-muted-foreground">
          資料來源：證交所 MI_MARGN，僅顯示原始餘額，變化率／券資比等分析將於 Step 4 完成。
        </p>
      </CardContent>
    </Card>
  );
}

export function InstitutionalPanel({ symbol }: { symbol: string }) {
  const { data, error } = useJson<{ history: InstitutionalRow[] }>(
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
        )}
        <p className="mt-2 text-xs text-muted-foreground">資料來源：證交所 T86，單位：股。</p>
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

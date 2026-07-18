"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { getRecentQueries, pushRecentQuery, type RecentQuery } from "@/lib/query-history";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type SearchResult = { symbol: string; name: string; market: string };

async function searchStocks(q: string): Promise<SearchResult[]> {
  if (!q.trim()) return [];
  try {
    const res = await fetch(`${API_URL}/api/v1/stocks/search?q=${encodeURIComponent(q.trim())}`);
    if (!res.ok) return [];
    const body: { results: SearchResult[] } = await res.json();
    return body.results;
  } catch {
    return [];
  }
}

export function StockSearch() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<SearchResult[]>([]);
  const [hint, setHint] = useState<string | null>(null);
  const [recent, setRecent] = useState<RecentQuery[]>([]);

  useEffect(() => {
    setRecent(getRecentQueries());
  }, []);

  useEffect(() => {
    const trimmed = query.trim();
    if (!trimmed) {
      setSuggestions([]);
      return;
    }
    const timer = setTimeout(async () => {
      setSuggestions(await searchStocks(trimmed));
    }, 250);
    return () => clearTimeout(timer);
  }, [query]);

  function goToAnalysis(result: SearchResult) {
    pushRecentQuery({ symbol: result.symbol, name: result.name });
    router.push(`/analyze/${encodeURIComponent(result.symbol)}`);
  }

  async function handleSubmit() {
    setHint(null);
    const trimmed = query.trim();
    if (!trimmed) return;

    const results = await searchStocks(trimmed);
    const exact = results.find((r) => r.symbol.toUpperCase() === trimmed.toUpperCase());
    if (exact) {
      goToAnalysis(exact);
      return;
    }
    if (results.length === 1) {
      goToAnalysis(results[0]);
      return;
    }
    if (results.length === 0) {
      setHint(`查無符合「${trimmed}」的股票，請確認代號或名稱是否正確。`);
      return;
    }
    setSuggestions(results);
    setHint("有多筆符合的股票，請從下面清單中選擇。");
  }

  return (
    <Card className="w-full max-w-md">
      <CardHeader>
        <CardTitle>股票分析</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            handleSubmit();
          }}
        >
          <Input
            placeholder="輸入股票代號或名稱，例如 2330 或 台積電"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
          <Button type="submit">分析</Button>
        </form>

        {hint && <p className="text-sm text-muted-foreground">{hint}</p>}

        {suggestions.length > 0 && (
          <ul className="divide-y rounded-md border">
            {suggestions.map((s) => (
              <li key={s.symbol}>
                <button
                  type="button"
                  className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-accent"
                  onClick={() => goToAnalysis(s)}
                >
                  <span className="font-medium">
                    {s.symbol} {s.name}
                  </span>
                  <span className="text-muted-foreground">{s.market}</span>
                </button>
              </li>
            ))}
          </ul>
        )}

        {suggestions.length === 0 && !hint && recent.length > 0 && (
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground">最近查詢</p>
            <ul className="flex flex-wrap gap-2">
              {recent.map((r) => (
                <li key={r.symbol}>
                  <button
                    type="button"
                    className="rounded-full border px-3 py-1 text-xs hover:bg-accent"
                    onClick={() => goToAnalysis({ symbol: r.symbol, name: r.name, market: "" })}
                  >
                    {r.symbol} {r.name}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

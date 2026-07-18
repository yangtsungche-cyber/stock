"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const MAX_SYMBOLS = 5;

type SearchResult = { symbol: string; name: string; market: string };
type Picked = { symbol: string; name: string };

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

export function BatchReport() {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<SearchResult[]>([]);
  const [picked, setPicked] = useState<Picked[]>([]);
  const [status, setStatus] = useState<"idle" | "generating" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

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

  function addPick(s: SearchResult) {
    if (picked.some((p) => p.symbol === s.symbol) || picked.length >= MAX_SYMBOLS) return;
    setPicked((prev) => [...prev, { symbol: s.symbol, name: s.name }]);
    setQuery("");
    setSuggestions([]);
  }

  function removePick(symbol: string) {
    setPicked((prev) => prev.filter((p) => p.symbol !== symbol));
  }

  async function generate() {
    setStatus("generating");
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/v1/stocks/batch-report`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbols: picked.map((p) => p.symbol) }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "批次分析報告.pdf";
      a.click();
      URL.revokeObjectURL(url);
      setStatus("idle");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus("error");
    }
  }

  return (
    <Card className="w-full max-w-md">
      <CardHeader>
        <CardTitle className="text-base">批次分析報告（最多 {MAX_SYMBOLS} 檔）</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">
          選好股票後直接產生 PDF 下載，不在頁面上顯示——查多檔時比較適合直接看報告。
        </p>

        {picked.length > 0 && (
          <ul className="flex flex-wrap gap-2">
            {picked.map((p) => (
              <li key={p.symbol}>
                <button
                  type="button"
                  className="rounded-full border px-3 py-1 text-xs hover:bg-accent"
                  onClick={() => removePick(p.symbol)}
                  title="點擊移除"
                >
                  {p.symbol} {p.name} ✕
                </button>
              </li>
            ))}
          </ul>
        )}

        {picked.length < MAX_SYMBOLS && (
          <>
            <Input
              placeholder="輸入股票代號或名稱"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            {suggestions.length > 0 && (
              <ul className="divide-y rounded-md border">
                {suggestions.map((s) => (
                  <li key={s.symbol}>
                    <button
                      type="button"
                      className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-accent"
                      onClick={() => addPick(s)}
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
          </>
        )}

        {picked.length >= MAX_SYMBOLS && (
          <p className="text-xs text-muted-foreground">已達 {MAX_SYMBOLS} 檔上限。</p>
        )}

        {error && <p className="text-sm text-muted-foreground">產生失敗：{error}</p>}

        <Button onClick={generate} disabled={picked.length === 0 || status === "generating"}>
          {status === "generating" ? "產生中…" : "產生 PDF"}
        </Button>
      </CardContent>
    </Card>
  );
}

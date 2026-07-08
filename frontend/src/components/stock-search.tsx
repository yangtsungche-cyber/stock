"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { searchMockStocks } from "@/lib/mock-stock";

export function StockSearch() {
  const router = useRouter();
  const [query, setQuery] = useState("");

  const suggestions = query.trim() ? searchMockStocks(query).slice(0, 5) : [];

  function goToAnalysis(symbol: string) {
    const trimmed = symbol.trim();
    if (!trimmed) return;
    router.push(`/analyze/${encodeURIComponent(trimmed)}`);
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
            goToAnalysis(query);
          }}
        >
          <Input
            placeholder="輸入股票代號或名稱，例如 2330"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
          <Button type="submit">分析</Button>
        </form>

        {suggestions.length > 0 && (
          <ul className="divide-y rounded-md border">
            {suggestions.map((s) => (
              <li key={s.symbol}>
                <button
                  type="button"
                  className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-accent"
                  onClick={() => goToAnalysis(s.symbol)}
                >
                  <span className="font-medium">{s.symbol}</span>
                  <span className="text-muted-foreground">{s.name}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

import { AnalysisTabs } from "@/components/analysis-tabs";
import { StockHeader } from "@/components/stock-header";
import { getMockStock } from "@/lib/mock-stock";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function fetchCompanyInfo(symbol: string) {
  try {
    const res = await fetch(`${API_URL}/api/v1/stocks/${encodeURIComponent(symbol)}/info`, {
      cache: "no-store",
    });
    if (!res.ok) return null;
    const data = await res.json();
    if (
      typeof data.name !== "string" ||
      (data.market !== "TWSE" && data.market !== "TPEx" && data.market !== "興櫃")
    ) {
      return null;
    }
    return { name: data.name as string, market: data.market as "TWSE" | "TPEx" | "興櫃" };
  } catch {
    return null;
  }
}

async function fetchLatestQuote(symbol: string) {
  try {
    const res = await fetch(
      `${API_URL}/api/v1/stocks/${encodeURIComponent(symbol)}/prices?interval=1d&period=5d`,
      { cache: "no-store" },
    );
    if (!res.ok) return null;
    const data = await res.json();
    const candles = data.candles as { close: number }[];
    if (candles.length < 1) return null;

    const latest = candles[candles.length - 1].close;
    const previous = candles.length >= 2 ? candles[candles.length - 2].close : latest;
    if (!Number.isFinite(latest) || !Number.isFinite(previous)) return null;

    const change = latest - previous;
    const changePercent = previous !== 0 ? (change / previous) * 100 : 0;

    return { price: latest, change, changePercent };
  } catch {
    return null;
  }
}

export default async function AnalyzePage({
  params,
}: {
  params: Promise<{ symbol: string }>;
}) {
  const { symbol } = await params;
  const decoded = decodeURIComponent(symbol);
  const mock = getMockStock(decoded);
  const [info, quote] = await Promise.all([fetchCompanyInfo(decoded), fetchLatestQuote(decoded)]);

  const stock = { ...mock, ...(info ?? {}), ...(quote ?? {}) };

  return (
    <div className="mx-auto w-full max-w-5xl flex-1 space-y-6 px-4 py-8">
      <StockHeader stock={stock} quoteUnavailable={!quote} />
      <AnalysisTabs symbol={stock.symbol} />
    </div>
  );
}

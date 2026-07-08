export type MockStock = {
  symbol: string;
  name: string;
  market: "TWSE" | "TPEx";
  price: number;
  change: number;
  changePercent: number;
};

const MOCK_STOCKS: Record<string, MockStock> = {
  "2330": { symbol: "2330", name: "台積電", market: "TWSE", price: 1015, change: 15, changePercent: 1.5 },
  "0050": { symbol: "0050", name: "元大台灣50", market: "TWSE", price: 187.3, change: -0.6, changePercent: -0.32 },
  "2317": { symbol: "2317", name: "鴻海", market: "TWSE", price: 203.5, change: 2.5, changePercent: 1.24 },
  "2454": { symbol: "2454", name: "聯發科", market: "TWSE", price: 1305, change: -10, changePercent: -0.76 },
};

export function getMockStock(symbol: string): MockStock {
  const key = symbol.trim().toUpperCase();
  return (
    MOCK_STOCKS[key] ?? {
      symbol: key,
      name: "未知股票（尚未串接真實資料源）",
      market: "TWSE",
      price: 0,
      change: 0,
      changePercent: 0,
    }
  );
}

export function searchMockStocks(query: string): MockStock[] {
  const q = query.trim().toUpperCase();
  if (!q) return Object.values(MOCK_STOCKS);
  return Object.values(MOCK_STOCKS).filter(
    (s) => s.symbol.includes(q) || s.name.includes(query.trim()),
  );
}

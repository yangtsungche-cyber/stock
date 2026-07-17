import Link from "next/link";
import { MarketScanPanel } from "@/components/market-scan-panel";
import { OvernightSentimentPanel } from "@/components/overnight-sentiment-panel";
import { StockSearch } from "@/components/stock-search";
import { SystemStatus } from "@/components/system-status";

export default function Home() {
  return (
    <div className="flex flex-1 flex-col items-center gap-8 px-4 py-16">
      <div className="text-center">
        <h1 className="text-3xl font-semibold tracking-tight">
          Jerry AI Stock Analyst Pro
        </h1>
        <p className="mt-2 text-muted-foreground">
          AI Technical Analysis Decision Engine
        </p>
      </div>
      <StockSearch />
      <div className="flex gap-4">
        <Link href="/watchlist" className="text-sm text-muted-foreground hover:text-foreground">
          管理自選股池 →
        </Link>
        <Link href="/verification" className="text-sm text-muted-foreground hover:text-foreground">
          分析驗證中心 →
        </Link>
      </div>
      <MarketScanPanel />
      <OvernightSentimentPanel />
      <SystemStatus />
    </div>
  );
}

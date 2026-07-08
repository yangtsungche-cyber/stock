import { StockSearch } from "@/components/stock-search";
import { SystemStatus } from "@/components/system-status";

export default function Home() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-8 px-4 py-16">
      <div className="text-center">
        <h1 className="text-3xl font-semibold tracking-tight">
          Jerry AI Stock Analyst Pro
        </h1>
        <p className="mt-2 text-muted-foreground">
          AI Technical Analysis Decision Engine
        </p>
      </div>
      <StockSearch />
      <SystemStatus />
    </div>
  );
}

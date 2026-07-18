import Link from "next/link";
import { PortfolioDashboard } from "@/components/portfolio-dashboard";

export default function PortfolioPage() {
  return (
    <div className="flex flex-1 flex-col items-center gap-4 px-4 py-16">
      <div className="w-full max-w-5xl">
        <Link href="/" className="text-sm text-muted-foreground hover:text-foreground">
          ← 回首頁
        </Link>
      </div>
      <PortfolioDashboard />
    </div>
  );
}

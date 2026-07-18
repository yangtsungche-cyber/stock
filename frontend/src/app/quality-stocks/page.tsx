import Link from "next/link";
import { QualityStocksList } from "@/components/quality-stocks-list";

export default function QualityStocksPage() {
  return (
    <div className="flex flex-1 flex-col items-center gap-4 px-4 py-16">
      <div className="w-full max-w-4xl">
        <Link href="/" className="text-sm text-muted-foreground hover:text-foreground">
          ← 回首頁
        </Link>
      </div>
      <QualityStocksList />
    </div>
  );
}

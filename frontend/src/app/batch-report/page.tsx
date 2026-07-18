import Link from "next/link";
import { BatchReport } from "@/components/batch-report";

export default function BatchReportPage() {
  return (
    <div className="flex flex-1 flex-col items-center gap-4 px-4 py-16">
      <div className="w-full max-w-md">
        <Link href="/" className="text-sm text-muted-foreground hover:text-foreground">
          ← 回首頁
        </Link>
      </div>
      <BatchReport />
    </div>
  );
}

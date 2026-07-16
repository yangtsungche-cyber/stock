import Link from "next/link";
import { VerificationCenter } from "@/components/verification-center";

export default function VerificationPage() {
  return (
    <div className="flex flex-1 flex-col items-center gap-4 px-4 py-16">
      <div className="w-full max-w-4xl">
        <Link href="/" className="text-sm text-muted-foreground hover:text-foreground">
          ← 回首頁
        </Link>
      </div>
      <VerificationCenter />
    </div>
  );
}

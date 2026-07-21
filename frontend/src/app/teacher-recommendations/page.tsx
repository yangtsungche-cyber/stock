import Link from "next/link";
import { TeacherRecommendationsManager } from "@/components/teacher-recommendations-manager";

export default function TeacherRecommendationsPage() {
  return (
    <div className="flex flex-1 flex-col items-center gap-4 px-4 py-16">
      <div className="w-full max-w-6xl">
        <Link href="/" className="text-sm text-muted-foreground hover:text-foreground">
          ← 回首頁
        </Link>
      </div>
      <TeacherRecommendationsManager />
    </div>
  );
}

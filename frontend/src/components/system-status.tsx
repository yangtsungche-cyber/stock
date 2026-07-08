"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type CheckState = "checking" | "ok" | "error";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const CHECKS: { label: string; path: string }[] = [
  { label: "FastAPI", path: "/api/v1/health" },
  { label: "PostgreSQL", path: "/api/v1/health/db" },
  { label: "Redis", path: "/api/v1/health/redis" },
];

function StatusBadge({ state }: { state: CheckState }) {
  if (state === "checking") return <Badge variant="secondary">檢查中…</Badge>;
  if (state === "ok") return <Badge className="bg-emerald-600 hover:bg-emerald-600">正常</Badge>;
  return <Badge variant="destructive">失敗</Badge>;
}

export function SystemStatus() {
  const [states, setStates] = useState<Record<string, CheckState>>(
    Object.fromEntries(CHECKS.map((c) => [c.label, "checking"])),
  );

  useEffect(() => {
    CHECKS.forEach(({ label, path }) => {
      fetch(`${API_URL}${path}`)
        .then((res) => {
          setStates((prev) => ({ ...prev, [label]: res.ok ? "ok" : "error" }));
        })
        .catch(() => {
          setStates((prev) => ({ ...prev, [label]: "error" }));
        });
    });
  }, []);

  return (
    <Card className="w-full max-w-md">
      <CardHeader>
        <CardTitle>系統連線狀態</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {CHECKS.map(({ label }) => (
          <div key={label} className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">{label}</span>
            <StatusBadge state={states[label]} />
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

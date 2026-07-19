"use client";

import { useTheme } from "next-themes";
import { useEffect, useRef, useState } from "react";
import {
  ColorType,
  createChart,
  createSeriesMarkers,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type HistoryPoint = {
  date: string;
  我: number | null;
  太太: number | null;
  女兒: number | null;
  "我+太太": number | null;
};

type Annotation = { id: number; date: string; note: string };

// 4 條線：我+太太合計、我、太太、女兒——顏色跟站上既有的紅漲/綠跌方向性配色無關（這是
// 「哪一條線」的區分，不是漲跌訊號），各給一個一眼能分辨的顏色。
const SERIES_CONFIG: { key: keyof HistoryPoint; label: string; color: string }[] = [
  { key: "我+太太", label: "我+太太合計", color: "#f59e0b" },
  { key: "我", label: "我", color: "#3b82f6" },
  { key: "太太", label: "太太", color: "#ec4899" },
  { key: "女兒", label: "女兒", color: "#22c55e" },
];

function toSeriesData(points: HistoryPoint[], key: keyof HistoryPoint) {
  return points
    .filter((p) => p[key] != null)
    .map((p) => ({ time: p.date as Time, value: p[key] as number }));
}

export function PortfolioValueChart() {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const markersPluginRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const primarySeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const { resolvedTheme } = useTheme();

  const [points, setPoints] = useState<HistoryPoint[]>([]);
  const [annotations, setAnnotations] = useState<Annotation[]>([]);
  const [status, setStatus] = useState<"loading" | "done" | "error">("loading");
  const [error, setError] = useState<string | null>(null);

  const [pendingDate, setPendingDate] = useState<string | null>(null);
  const [noteText, setNoteText] = useState("");
  const [saving, setSaving] = useState(false);

  async function loadData() {
    setStatus("loading");
    setError(null);
    try {
      const [historyRes, annotationsRes] = await Promise.all([
        fetch(`${API_URL}/api/v1/portfolio/history`),
        fetch(`${API_URL}/api/v1/portfolio/annotations`),
      ]);
      if (!historyRes.ok) throw new Error(`HTTP ${historyRes.status}`);
      if (!annotationsRes.ok) throw new Error(`HTTP ${annotationsRes.status}`);
      const historyBody: { points: HistoryPoint[] } = await historyRes.json();
      const annotationsBody: { annotations: Annotation[] } = await annotationsRes.json();
      setPoints(historyBody.points);
      setAnnotations(annotationsBody.annotations);
      setStatus("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus("error");
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    if (!containerRef.current || status !== "done") return;

    const isDark = resolvedTheme === "dark";
    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: isDark ? "#a1a1aa" : "#52525b",
      },
      grid: {
        vertLines: { color: isDark ? "#27272a" : "#e4e4e7" },
        horzLines: { color: isDark ? "#27272a" : "#e4e4e7" },
      },
      timeScale: { borderVisible: false },
      rightPriceScale: { borderVisible: false },
    });

    let primarySeries: ISeriesApi<"Line"> | null = null;
    for (const cfg of SERIES_CONFIG) {
      const series = chart.addSeries(LineSeries, { color: cfg.color, title: cfg.label, lineWidth: 2 });
      series.setData(toSeriesData(points, cfg.key));
      if (cfg.key === "我+太太") primarySeries = series;
    }
    primarySeriesRef.current = primarySeries;

    if (primarySeries) {
      markersPluginRef.current = createSeriesMarkers(primarySeries, []);
    }

    chart.subscribeClick((param) => {
      if (!param.time) return;
      setPendingDate(String(param.time));
    });

    chart.timeScale().fitContent();
    chartRef.current = chart;

    return () => {
      chart.remove();
      chartRef.current = null;
      markersPluginRef.current = null;
      primarySeriesRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [points, resolvedTheme, status]);

  useEffect(() => {
    if (!markersPluginRef.current) return;
    const markers: SeriesMarker<Time>[] = annotations.map((a) => ({
      time: a.date as Time,
      position: "aboveBar",
      color: "#f59e0b",
      shape: "circle",
      text: a.note,
    }));
    markersPluginRef.current.setMarkers(markers);
  }, [annotations]);

  const existingAnnotation = pendingDate ? annotations.find((a) => a.date === pendingDate) : null;

  async function saveAnnotation() {
    if (!pendingDate || !noteText.trim()) return;
    setSaving(true);
    try {
      const res = await fetch(`${API_URL}/api/v1/portfolio/annotations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ date: pendingDate, note: noteText.trim() }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const created: Annotation = await res.json();
      setAnnotations((prev) => [...prev, created]);
      setPendingDate(null);
      setNoteText("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  async function deleteAnnotation(id: number) {
    try {
      const res = await fetch(`${API_URL}/api/v1/portfolio/annotations/${id}`, { method: "DELETE" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setAnnotations((prev) => prev.filter((a) => a.id !== id));
      setPendingDate(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div className="space-y-2">
      <p className="text-sm text-muted-foreground">
        市值每個交易日收盤後自動記錄一筆快照，累積夠多天數才會看到走勢。點圖上任一位置可以為那天加註記
        （例如大筆支出、匯入資金等），方便日後回顧市值變化的原因。
      </p>
      {status === "loading" && <p className="text-sm text-muted-foreground">讀取中…</p>}
      {status === "error" && <p className="text-sm text-muted-foreground">讀取失敗：{error}</p>}
      {status === "done" && points.length === 0 && (
        <p className="text-sm text-muted-foreground">目前還沒有任何市值快照紀錄，明天收盤後排程會自動開始累積。</p>
      )}
      {status === "done" && points.length > 0 && <div ref={containerRef} className="h-[400px] w-full" />}

      <Dialog open={pendingDate !== null} onOpenChange={(open) => !open && setPendingDate(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{pendingDate} 的註記</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            {existingAnnotation && (
              <div className="rounded-lg border p-2 text-sm">
                <p>{existingAnnotation.note}</p>
                <Button
                  variant="ghost"
                  size="sm"
                  className="mt-1 text-destructive"
                  onClick={() => deleteAnnotation(existingAnnotation.id)}
                >
                  刪除這筆註記
                </Button>
              </div>
            )}
            <Input
              placeholder="例如：這天匯出一筆大額支出"
              value={noteText}
              onChange={(e) => setNoteText(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button onClick={saveAnnotation} disabled={saving || !noteText.trim()}>
              {saving ? "儲存中…" : "新增註記"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

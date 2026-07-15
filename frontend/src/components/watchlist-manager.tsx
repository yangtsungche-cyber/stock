"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Category = "核心" | "波段" | "觀察";

type WatchlistEntry = {
  id: number;
  stock_code: string;
  stock_name: string;
  category: Category;
  enabled: boolean;
  note: string | null;
  created_at: string;
};

const CATEGORY_COLOR: Record<Category, string> = {
  核心: "bg-red-600 hover:bg-red-600",
  波段: "bg-amber-600 hover:bg-amber-600",
  觀察: "bg-muted-foreground/60 hover:bg-muted-foreground/60",
};

async function fetchWatchlist(): Promise<WatchlistEntry[]> {
  const res = await fetch(`${API_URL}/api/v1/watchlist`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function AddEntryDialog({ onAdded }: { onAdded: () => void }) {
  const [open, setOpen] = useState(false);
  const [stockCode, setStockCode] = useState("");
  const [stockName, setStockName] = useState("");
  const [category, setCategory] = useState<Category>("觀察");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/v1/watchlist`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          stock_code: stockCode.trim(),
          stock_name: stockName.trim(),
          category,
          note: note.trim() || null,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      setStockCode("");
      setStockName("");
      setCategory("觀察");
      setNote("");
      setOpen(false);
      onAdded();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" />}>新增自選股</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>新增自選股</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">股票代號</label>
            <Input value={stockCode} onChange={(e) => setStockCode(e.target.value)} placeholder="例如 2330" />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">股票名稱</label>
            <Input value={stockName} onChange={(e) => setStockName(e.target.value)} placeholder="例如 台積電" />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">分類</label>
            <Select value={category} onValueChange={(v) => setCategory(v as Category)}>
              <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="核心">核心</SelectItem>
                <SelectItem value="波段">波段</SelectItem>
                <SelectItem value="觀察">觀察</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">備註（選填）</label>
            <Input value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button
            onClick={submit}
            disabled={submitting || !stockCode.trim() || !stockName.trim()}
          >
            {submitting ? "新增中…" : "新增"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function EditEntryDialog({ entry, onUpdated }: { entry: WatchlistEntry; onUpdated: () => void }) {
  const [open, setOpen] = useState(false);
  const [category, setCategory] = useState<Category>(entry.category);
  const [note, setNote] = useState(entry.note ?? "");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/v1/watchlist/${entry.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category, note: note.trim() || null }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      setOpen(false);
      onUpdated();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" variant="outline" />}>編輯</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>編輯 {entry.stock_code} {entry.stock_name}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">分類</label>
            <Select value={category} onValueChange={(v) => setCategory(v as Category)}>
              <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="核心">核心</SelectItem>
                <SelectItem value="波段">波段</SelectItem>
                <SelectItem value="觀察">觀察</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">備註</label>
            <Input value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button onClick={submit} disabled={submitting}>{submitting ? "儲存中…" : "儲存"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function WatchlistManager() {
  const [entries, setEntries] = useState<WatchlistEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  function reload() {
    fetchWatchlist().then(setEntries).catch((err) => setError(err.message));
  }

  useEffect(() => {
    reload();
  }, []);

  async function toggleEnabled(entry: WatchlistEntry) {
    await fetch(`${API_URL}/api/v1/watchlist/${entry.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: !entry.enabled }),
    });
    reload();
  }

  async function remove(entry: WatchlistEntry) {
    if (!window.confirm(`確定要移除 ${entry.stock_code} ${entry.stock_name}？`)) return;
    await fetch(`${API_URL}/api/v1/watchlist/${entry.id}`, { method: "DELETE" });
    reload();
  }

  return (
    <Card className="w-full max-w-3xl">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base">自選股池</CardTitle>
        <AddEntryDialog onAdded={reload} />
      </CardHeader>
      <CardContent>
        {error && <p className="text-sm text-muted-foreground">無法取得資料：{error}</p>}
        {!entries && !error && <Skeleton className="h-40 w-full" />}
        {entries && entries.length === 0 && (
          <p className="text-sm text-muted-foreground">自選股池是空的，點右上角新增。</p>
        )}
        {entries && entries.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-muted-foreground">
                <tr className="text-left">
                  <th className="py-1 pr-2">代號</th>
                  <th className="py-1 pr-2">名稱</th>
                  <th className="py-1 pr-2">分類</th>
                  <th className="py-1 pr-2">狀態</th>
                  <th className="py-1 pr-2">備註</th>
                  <th className="py-1 pr-2 text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr key={entry.id} className="border-t">
                    <td className="py-1.5 pr-2 font-medium">{entry.stock_code}</td>
                    <td className="py-1.5 pr-2">{entry.stock_name}</td>
                    <td className="py-1.5 pr-2">
                      <Badge className={CATEGORY_COLOR[entry.category]}>{entry.category}</Badge>
                    </td>
                    <td className="py-1.5 pr-2">
                      <button
                        onClick={() => toggleEnabled(entry)}
                        className={entry.enabled ? "text-foreground" : "text-muted-foreground"}
                      >
                        {entry.enabled ? "啟用中" : "已停用"}
                      </button>
                    </td>
                    <td className="py-1.5 pr-2 text-muted-foreground">{entry.note ?? "—"}</td>
                    <td className="py-1.5 pr-2">
                      <div className="flex justify-end gap-2">
                        <EditEntryDialog entry={entry} onUpdated={reload} />
                        <Button size="sm" variant="destructive" onClick={() => remove(entry)}>
                          刪除
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

"use client";

import { useState, type ReactNode } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

// 給表頭欄位用的「?」說明按鈕——點開一個 Dialog 解釋這個分數/等級的算法跟意義。
// 表頭本身有排序用的 onClick，所以這裡一定要 stopPropagation，不然點「?」會連帶觸發排序。
export function InfoTip({ title, children }: { title: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        aria-label={`說明：${title}`}
        className="ml-1 inline-flex h-3.5 w-3.5 items-center justify-center rounded-full border border-muted-foreground/50 align-middle text-[10px] leading-none text-muted-foreground hover:border-foreground hover:text-foreground"
        onClick={(e) => {
          e.stopPropagation();
          setOpen(true);
        }}
      >
        ?
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-md" onClick={(e) => e.stopPropagation()}>
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
          </DialogHeader>
          <div className="space-y-2 text-left text-sm font-normal text-muted-foreground">
            {children}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

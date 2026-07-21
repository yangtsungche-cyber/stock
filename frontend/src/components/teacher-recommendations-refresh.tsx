"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type ProviderKey = "chatgpt" | "claude" | "gemini";
const PROVIDER_LABEL: Record<ProviderKey, string> = {
  chatgpt: "ChatGPT",
  claude: "Claude",
  gemini: "Gemini",
};

type ProviderResult = { errors: string[]; missing_symbols: string[] } | null;

type ParsedField = {
  main_industry: string | null;
  long_term_rating: number | null;
  investment_category: string | null;
  ai_benefit_rating: number | null;
  volatility: string | null;
  suitable_strategy: string | null;
};

type Change = {
  id: number;
  symbol: string;
  name: string;
  current: ParsedField;
  reconciled: ParsedField;
  sources: Record<ProviderKey, (ParsedField & { unrecognized: boolean }) | null>;
  unrecognized: boolean;
};

function fieldLabel(v: string | number | null): string {
  if (v === null || v === undefined) return "—";
  return String(v);
}

export function TeacherRecommendationsRefresh({ onSaved }: { onSaved: () => void }) {
  const [showPrompt, setShowPrompt] = useState(false);
  const [prompt, setPrompt] = useState<string | null>(null);
  const [promptError, setPromptError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const [showPaste, setShowPaste] = useState(false);
  const [texts, setTexts] = useState<Record<ProviderKey, string>>({ chatgpt: "", claude: "", gemini: "" });
  const [parseStatus, setParseStatus] = useState<"idle" | "parsing" | "done" | "error">("idle");
  const [parseError, setParseError] = useState<string | null>(null);
  const [providers, setProviders] = useState<Record<ProviderKey, ProviderResult>>({
    chatgpt: null, claude: null, gemini: null,
  });
  const [changes, setChanges] = useState<Change[]>([]);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "done" | "error">("idle");

  async function generatePrompt() {
    setPromptError(null);
    setShowPrompt(true);
    try {
      const res = await fetch(`${API_URL}/api/v1/teacher-recommendations/refresh-prompt`);
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      const body: { prompt: string } = await res.json();
      setPrompt(body.prompt);
    } catch (err) {
      setPromptError(err instanceof Error ? err.message : String(err));
    }
  }

  async function copyPrompt() {
    if (!prompt) return;
    await navigator.clipboard.writeText(prompt);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  async function parseReplies() {
    setParseStatus("parsing");
    setParseError(null);
    try {
      const res = await fetch(`${API_URL}/api/v1/teacher-recommendations/refresh/parse`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(texts),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      const body: { providers: Record<ProviderKey, ProviderResult>; changes: Change[] } = await res.json();
      setProviders(body.providers);
      setChanges(body.changes);
      setParseStatus("done");
    } catch (err) {
      setParseError(err instanceof Error ? err.message : String(err));
      setParseStatus("error");
    }
  }

  async function saveReconciled() {
    setSaveStatus("saving");
    try {
      const res = await fetch(`${API_URL}/api/v1/teacher-recommendations/refresh/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(texts),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      setSaveStatus("done");
      setShowPaste(false);
      setTexts({ chatgpt: "", claude: "", gemini: "" });
      setParseStatus("idle");
      setChanges([]);
      onSaved();
    } catch (err) {
      setParseError(err instanceof Error ? err.message : String(err));
      setSaveStatus("error");
    }
  }

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle className="text-base">重新整理 AI 綜合評判</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          這個 App 不會直接呼叫任何付費 LLM API——請按下方按鈕產生提示文字，自行貼到
          ChatGPT／Gemini／Claude 詢問，再把三家的回答貼回下面，由這裡做規則式整合（多數決 +
          平均），不是再一次 AI 呼叫。
        </p>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={generatePrompt}>
            產生 AI 提示文字
          </Button>
          <Button size="sm" variant="outline" onClick={() => setShowPaste((v) => !v)}>
            {showPaste ? "收起貼上區" : "貼上三家 AI 回答"}
          </Button>
        </div>

        {showPrompt && (
          <div className="space-y-2 rounded-md border p-3">
            {promptError && <p className="text-sm text-destructive">{promptError}</p>}
            {prompt && (
              <>
                <textarea
                  readOnly
                  value={prompt}
                  className="h-40 w-full rounded-md border bg-muted/30 p-2 font-mono text-xs"
                />
                <Button size="sm" onClick={copyPrompt}>{copied ? "已複製" : "複製到剪貼簿"}</Button>
              </>
            )}
          </div>
        )}

        {showPaste && (
          <div className="space-y-3 rounded-md border p-3">
            {(Object.keys(PROVIDER_LABEL) as ProviderKey[]).map((p) => (
              <div key={p} className="space-y-1">
                <label className="text-xs text-muted-foreground">{PROVIDER_LABEL[p]} 的回答（選填）</label>
                <textarea
                  value={texts[p]}
                  onChange={(e) => setTexts((t) => ({ ...t, [p]: e.target.value }))}
                  placeholder={"代號|主要產業|長期評價|投資分類|AI受惠程度|波動程度|適合策略"}
                  className="h-24 w-full rounded-md border p-2 font-mono text-xs"
                />
              </div>
            ))}
            {parseError && <p className="text-sm text-destructive">{parseError}</p>}
            <Button
              size="sm"
              onClick={parseReplies}
              disabled={parseStatus === "parsing" || Object.values(texts).every((t) => !t.trim())}
            >
              {parseStatus === "parsing" ? "解析中…" : "解析並比對"}
            </Button>

            {parseStatus === "done" && (
              <div className="space-y-3">
                {(Object.keys(PROVIDER_LABEL) as ProviderKey[]).map((p) => {
                  const r = providers[p];
                  if (!r) return null;
                  return (
                    <div key={p} className="text-xs text-muted-foreground">
                      <span className="font-medium text-foreground">{PROVIDER_LABEL[p]}</span>
                      {r.errors.length > 0 && (
                        <ul className="list-disc pl-4 text-destructive">
                          {r.errors.map((e, i) => <li key={i}>{e}</li>)}
                        </ul>
                      )}
                      {r.missing_symbols.length > 0 && (
                        <p>未提及 {r.missing_symbols.length} 檔股票（這些股票不會被這次更新影響）</p>
                      )}
                    </div>
                  );
                })}

                {changes.length === 0 && (
                  <p className="text-sm text-muted-foreground">沒有偵測到任何股票的異動。</p>
                )}
                {changes.length > 0 && (
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead className="text-muted-foreground">
                        <tr className="text-left">
                          <th className="py-1 pr-2">股票</th>
                          <th className="py-1 pr-2">主要產業</th>
                          <th className="py-1 pr-2">長期評價</th>
                          <th className="py-1 pr-2">投資分類</th>
                          <th className="py-1 pr-2">AI受惠</th>
                          <th className="py-1 pr-2">波動</th>
                          <th className="py-1 pr-2">策略</th>
                        </tr>
                      </thead>
                      <tbody>
                        {changes.map((c) => (
                          <tr key={c.id} className={`border-t ${c.unrecognized ? "bg-amber-500/10" : ""}`}>
                            <td className="py-1 pr-2 font-medium">{c.symbol} {c.name}</td>
                            <td className="py-1 pr-2">{fieldLabel(c.reconciled.main_industry)}</td>
                            <td className="py-1 pr-2">{fieldLabel(c.reconciled.long_term_rating)}</td>
                            <td className="py-1 pr-2">{fieldLabel(c.reconciled.investment_category)}</td>
                            <td className="py-1 pr-2">{fieldLabel(c.reconciled.ai_benefit_rating)}</td>
                            <td className="py-1 pr-2">{fieldLabel(c.reconciled.volatility)}</td>
                            <td className="py-1 pr-2">{fieldLabel(c.reconciled.suitable_strategy)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {changes.some((c) => c.unrecognized) && (
                      <p className="mt-1 text-xs text-amber-600">
                        橘底列有欄位不在允許的固定選項中，請確認 AI 回答是否符合格式。
                      </p>
                    )}
                  </div>
                )}

                <Button
                  size="sm"
                  onClick={saveReconciled}
                  disabled={saveStatus === "saving" || changes.length === 0}
                >
                  {saveStatus === "saving" ? "儲存中…" : `儲存（${changes.length} 檔異動）`}
                </Button>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

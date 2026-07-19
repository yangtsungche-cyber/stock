"use client";

// 後端沒有帳號系統，只靠共用密鑰擋掉直接打裸 Cloud Run URL 的存取（見
// backend/app/main.py 的 require_api_key）。這裡沒有集中的 API client 可以統一加
// header——約 20 個元件各自呼叫 fetch()——所以在 module 最上層（元件掛載前、
// script 一被載入就執行）直接 monkey-patch window.fetch，比逐一改每個呼叫點風險低。
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_BACKEND_API_KEY;

declare global {
  interface Window {
    __apiKeyFetchPatched?: boolean;
  }
}

if (typeof window !== "undefined" && API_KEY && !window.__apiKeyFetchPatched) {
  window.__apiKeyFetchPatched = true;
  const originalFetch = window.fetch.bind(window);
  window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
    const url =
      typeof input === "string"
        ? input
        : input instanceof URL
          ? input.toString()
          : input.url;
    if (url.startsWith(API_URL)) {
      const headers = new Headers(init?.headers);
      headers.set("X-API-Key", API_KEY);
      return originalFetch(input, { ...init, headers });
    }
    return originalFetch(input, init);
  };
}

export function ApiKeyFetchPatch() {
  return null;
}

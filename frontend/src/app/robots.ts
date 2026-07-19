import type { MetadataRoute } from "next";

// 個人持股/財務資料網站，不希望被搜尋引擎索引——雙重保險：這裡擋掉所有爬蟲的
// /robots.txt，加上 layout.tsx 的 <meta name="robots"> 標籤（有些爬蟲只看其中一個）。
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      disallow: "/",
    },
  };
}

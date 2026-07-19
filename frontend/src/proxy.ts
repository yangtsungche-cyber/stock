import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { SITE_AUTH_COOKIE, isValidAuthToken } from "@/lib/site-auth";

// 全站密碼閘——這個網站含有真實個人持股/財務資料，不希望公開存取。`matcher` 排除
// /login（含它的登入 Server Action，同一個路徑）跟靜態資源，其餘所有路徑都要先驗證
// cookie 才放行，沒有就導去 /login。
export function proxy(request: NextRequest) {
  const token = request.cookies.get(SITE_AUTH_COOKIE)?.value;
  if (isValidAuthToken(token)) {
    return NextResponse.next();
  }

  const loginUrl = new URL("/login", request.url);
  loginUrl.searchParams.set("next", request.nextUrl.pathname);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: [
    "/((?!login|_next/static|_next/image|favicon.ico|robots.txt).*)",
  ],
};

import { createHash, timingSafeEqual } from "crypto";

// 個人持股/財務資料網站，用單一共用密碼擋掉未授權訪問——不是多使用者帳號系統，
// 不需要資料庫/使用者表，用一個環境變數存密碼即可。Cookie 裡存密碼的雜湊值而不是明文，
// 避免萬一 cookie 外洩就直接曝光密碼本身。
export const SITE_AUTH_COOKIE = "site_auth";

function hash(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}

export function expectedAuthToken(): string | null {
  const password = process.env.SITE_PASSWORD;
  return password ? hash(password) : null;
}

export function isValidAuthToken(token: string | undefined | null): boolean {
  const expected = expectedAuthToken();
  if (!expected || !token) return false;
  const a = Buffer.from(token);
  const b = Buffer.from(expected);
  if (a.length !== b.length) return false;
  return timingSafeEqual(a, b);
}

export function isValidPassword(password: string): boolean {
  const expected = process.env.SITE_PASSWORD;
  if (!expected) return false;
  const a = Buffer.from(password);
  const b = Buffer.from(expected);
  if (a.length !== b.length) return false;
  return timingSafeEqual(a, b);
}

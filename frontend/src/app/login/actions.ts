"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { SITE_AUTH_COOKIE, expectedAuthToken, isValidPassword } from "@/lib/site-auth";

export async function login(formData: FormData) {
  const password = formData.get("password");
  const next = typeof formData.get("next") === "string" ? (formData.get("next") as string) : "/";

  if (typeof password !== "string" || !isValidPassword(password)) {
    redirect(`/login?error=1&next=${encodeURIComponent(next)}`);
  }

  const token = expectedAuthToken();
  const cookieStore = await cookies();
  cookieStore.set(SITE_AUTH_COOKIE, token!, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 30, // 30 天
  });

  redirect(next.startsWith("/") ? next : "/");
}

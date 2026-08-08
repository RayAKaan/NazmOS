import { NextResponse } from "next/server";
import { ACCESS_COOKIE, REFRESH_COOKIE, SESSION_COOKIE } from "@/lib/session";

export async function POST() {
  const res = NextResponse.json({ ok: true });
  res.cookies.delete(ACCESS_COOKIE);
  res.cookies.delete(REFRESH_COOKIE);
  res.cookies.delete(SESSION_COOKIE);
  return res;
}

import { NextRequest, NextResponse } from "next/server";
import {
  ACCESS_COOKIE,
  REFRESH_COOKIE,
  SESSION_COOKIE,
  ACCESS_MAX_AGE,
  REFRESH_MAX_AGE,
  cookieOptions,
} from "@/lib/session";

export async function POST(req: NextRequest) {
  let body: { access_token?: string; refresh_token?: string } = {};
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid body" }, { status: 400 });
  }

  const { access_token, refresh_token } = body;
  if (!access_token) {
    return NextResponse.json({ error: "Missing access_token" }, { status: 400 });
  }

  const res = NextResponse.json({ ok: true });
  res.cookies.set(ACCESS_COOKIE, access_token, cookieOptions(ACCESS_MAX_AGE));
  res.cookies.set(
    REFRESH_COOKIE,
    refresh_token || "",
    cookieOptions(REFRESH_MAX_AGE, "/api/auth")
  );
  res.cookies.set(SESSION_COOKIE, "1", {
    ...cookieOptions(REFRESH_MAX_AGE),
    httpOnly: false,
  });
  return res;
}

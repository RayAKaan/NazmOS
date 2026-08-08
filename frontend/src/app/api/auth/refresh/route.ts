import { NextRequest, NextResponse } from "next/server";
import {
  ACCESS_COOKIE,
  REFRESH_COOKIE,
  SESSION_COOKIE,
  ACCESS_MAX_AGE,
  REFRESH_MAX_AGE,
  cookieOptions,
} from "@/lib/session";

const API_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function POST(req: NextRequest) {
  const refreshToken = req.cookies.get(REFRESH_COOKIE)?.value;
  if (!refreshToken) {
    return NextResponse.json({ error: "No refresh token" }, { status: 401 });
  }

  let backendRes: Response;
  try {
    backendRes = await fetch(`${API_URL}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
  } catch {
    return NextResponse.json({ error: "Upstream unreachable" }, { status: 502 });
  }

  if (!backendRes.ok) {
    const res = NextResponse.json({ error: "Refresh failed" }, { status: 401 });
    res.cookies.delete(ACCESS_COOKIE);
    res.cookies.delete(SESSION_COOKIE);
    return res;
  }

  const data = await backendRes.json();
  const res = NextResponse.json({ ok: true });
  res.cookies.set(ACCESS_COOKIE, data.access_token, cookieOptions(ACCESS_MAX_AGE));
  res.cookies.set(SESSION_COOKIE, "1", {
    ...cookieOptions(REFRESH_MAX_AGE),
    httpOnly: false,
  });
  return res;
}

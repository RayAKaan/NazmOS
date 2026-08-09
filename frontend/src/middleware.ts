import { NextRequest, NextResponse } from "next/server";
import { ACCESS_COOKIE, SESSION_COOKIE } from "@/lib/session";

const PROTECTED_SEGMENTS = [
  "feed",
  "dashboard",
  "orchestrator",
  "money-audit",
  "recovery-match",
  "upload",
  "ops",
  "team",
  "settings",
  "integrations",
  "chain",
];

// Auth pages: already-authenticated users are sent to their dashboard.
const AUTH_SEGMENTS = ["login", "register"];

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // Inject the access token from the httpOnly cookie into proxied API calls.
  // The backend only ever sees the Bearer header, never the cookie.
  if (pathname.startsWith("/api/v1")) {
    const token = req.cookies.get(ACCESS_COOKIE)?.value;
    if (!token) {
      return NextResponse.next();
    }
    const headers = new Headers(req.headers);
    headers.set("Authorization", `Bearer ${token}`);
    return NextResponse.next({ request: { headers } });
  }

  const loggedIn = req.cookies.get(SESSION_COOKIE)?.value === "1";
  const firstSegment = pathname.split("/")[1];

  // Authenticated users should not see login/register.
  if (loggedIn && AUTH_SEGMENTS.includes(firstSegment)) {
    const url = req.nextUrl.clone();
    url.pathname = "/dashboard";
    url.search = "";
    return NextResponse.redirect(url);
  }

  // Guard dashboard routes on the server (authentication only; capability
  // gating happens client-side from the server-declared capabilities object).
  if (PROTECTED_SEGMENTS.includes(firstSegment)) {
    if (!loggedIn) {
      const url = req.nextUrl.clone();
      url.pathname = "/login";
      url.search = "";
      return NextResponse.redirect(url);
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/api/v1/:path*",
    "/login/:path*",
    "/register/:path*",
    "/feed/:path*",
    "/dashboard/:path*",
    "/orchestrator/:path*",
    "/money-audit/:path*",
    "/recovery-match/:path*",
    "/upload/:path*",
    "/ops/:path*",
    "/team/:path*",
    "/settings/:path*",
    "/integrations/:path*",
    "/chain/:path*",
  ],
};

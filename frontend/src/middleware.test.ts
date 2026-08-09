import { middleware } from "@/middleware";
import { ACCESS_COOKIE, SESSION_COOKIE } from "@/lib/session";

jest.mock("next/server", () => {
  class NextRequest {}
  const NextResponse = {
    next: (opts?: { request?: { headers?: Headers } }) => ({ status: 200, opts }),
    redirect: (url: { pathname?: string } | string) => {
      const location =
        typeof url === "string" ? url : url.pathname || "/dashboard";
      return { status: 307, headers: new Headers({ location }), url };
    },
  };
  return { NextRequest, NextResponse };
});

function fakeRequest(pathname: string, cookies: Record<string, string>) {
  return {
    url: `http://test${pathname}`,
    headers: new Headers(),
    cookies: {
      get: (name: string) =>
        name in cookies ? { name, value: cookies[name] } : undefined,
    },
    nextUrl: {
      pathname,
      search: "",
      clone: () => ({ pathname, search: "", pathname2: pathname }),
    },
  } as any;
}

describe("middleware", () => {
  it("redirects unauthenticated visitors away from dashboard routes to /login", () => {
    const res = middleware(fakeRequest("/dashboard", {}));
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toBe("/login");
  });

  it("redirects authenticated users away from /login to /dashboard", () => {
    const res = middleware(fakeRequest("/login", { [SESSION_COOKIE]: "1" }));
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toBe("/dashboard");
  });

  it("redirects authenticated users away from /register to /dashboard", () => {
    const res = middleware(fakeRequest("/register", { [SESSION_COOKIE]: "1" }));
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toBe("/dashboard");
  });

  it("injects the access token into proxied API calls without exposing the cookie", () => {
    const res: any = middleware(
      fakeRequest("/api/v1/auth/me", { [ACCESS_COOKIE]: "jwt-abc" })
    );
    expect(res.status).toBe(200);
    const injected = res.opts.request.headers.get("Authorization");
    expect(injected).toBe("Bearer jwt-abc");
  });

  it("allows an authenticated founder through /ops (capability gated client-side)", () => {
    const res = middleware(fakeRequest("/ops", { [SESSION_COOKIE]: "1" }));
    expect(res.status).toBe(200);
  });
});

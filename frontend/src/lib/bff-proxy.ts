/**
 * Pure BFF proxy core — forwards same-origin `/api/v1/*` calls from the Next.js
 * server to the configured internal FastAPI backend.
 *
 * Kept framework-agnostic (no `next/server` imports) so the proxying behaviour
 * is unit-testable in isolation. The Next.js route handler
 * (`src/app/api/v1/[...path]/route.ts`) is a thin wrapper over this module.
 *
 * Security invariants:
 *  - The destination is ALWAYS the configured `API_URL` — never a value taken
 *    from the incoming request — so this cannot become an open proxy.
 *  - Only an explicit allowlist of request/response headers is forwarded, so
 *    backend credentials, cookies, and Next.js/server env-derived headers are
 *    never leaked to (or from) the upstream.
 */

const DEFAULT_API_URL = "http://localhost:8000";

/** Request headers the browser may relay to the FastAPI backend. */
const REQUEST_HEADER_ALLOWLIST = new Set([
  "content-type",
  "accept",
  "authorization",
  "accept-language",
  "cache-control",
  "if-none-match",
  "if-modified-since",
]);

/** Response headers we choose to relay back to the browser. */
const RESPONSE_HEADER_ALLOWLIST = new Set([
  "content-type",
  "x-guest-session-id",
  "cache-control",
  "etag",
  "x-ratelimit-limit",
  "x-ratelimit-window",
]);

/**
 * Normalise and validate the configured API base URL. Throws on non-HTTP(S)
 * schemes or malformed URLs so an unsafe destination can never be constructed.
 */
export function normalizeApiUrl(raw?: string | null): string {
  const value = (raw ?? "").trim().replace(/\/+$/, "");
  const base =
    value ||
    process.env.API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    DEFAULT_API_URL;
  const trimmed = base.trim().replace(/\/+$/, "");
  let parsed: URL;
  try {
    parsed = new URL(trimmed);
  } catch {
    throw new Error("Invalid API_URL");
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new Error("Invalid API_URL scheme");
  }
  return parsed.toString().replace(/\/+$/, "");
}

/**
 * Resolve the effective API base URL for this request.
 */
export function resolveApiUrl(): string {
  return normalizeApiUrl();
}

/**
 * Build the absolute upstream URL for a `/api/v1/*` path. The path segments
 * come from the Next.js catch-all and are percent-encoded to prevent URL
 * injection; the origin is always the configured API_URL.
 */
export function buildUpstreamUrl(
  pathSegments: string[],
  search: string | undefined,
  apiUrl?: string
): string {
  const base = normalizeApiUrl(apiUrl);
  const encodedPath = pathSegments
    .map((segment) => encodeURIComponent(segment))
    .join("/");
  const path = encodedPath ? `/${encodedPath}` : "";
  const rawQuery = search && search.length > 0 ? search : "";
  const query =
    rawQuery && !rawQuery.startsWith("?") ? `?${rawQuery}` : rawQuery;
  return `${base}/api/v1${path}${query}`;
}

/**
 * Forward the request to the backend and return a Response that preserves the
 * upstream status, body and allowlisted headers.
 */
export async function proxyToBackend(opts: {
  pathSegments: string[];
  search?: string;
  method: string;
  headers?: Headers | Record<string, string>;
  body?: BodyInit | null;
  apiUrl?: string;
}): Promise<Response> {
  const url = buildUpstreamUrl(opts.pathSegments, opts.search, opts.apiUrl);

  const upstreamHeaders = new Headers();
  const sourceHeaders =
    opts.headers instanceof Headers
      ? opts.headers
      : new Headers(opts.headers ?? {});
  sourceHeaders.forEach((value, key) => {
    const lower = key.toLowerCase();
    if (REQUEST_HEADER_ALLOWLIST.has(lower)) {
      upstreamHeaders.set(lower, value);
    }
  });

  let res: Response;
  try {
    res = await fetch(url, {
      method: opts.method,
      headers: upstreamHeaders,
      body: opts.body,
    });
  } catch {
    throw new ProxyUpstreamError(
      `Failed to reach the backend at ${url.split("/api/v1")[0]}`
    );
  }

  const responseHeaders = new Headers();
  res.headers.forEach((value, key) => {
    const lower = key.toLowerCase();
    if (RESPONSE_HEADER_ALLOWLIST.has(lower)) {
      responseHeaders.set(lower, value);
    }
  });

  const bodyBuffer = await res.arrayBuffer();
  return new Response(bodyBuffer, {
    status: res.status,
    headers: responseHeaders,
  });
}

/** Raised when the upstream backend cannot be reached at all. */
export class ProxyUpstreamError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ProxyUpstreamError";
  }
}

import { NextRequest } from "next/server";
import {
  proxyToBackend,
  ProxyUpstreamError,
} from "@/lib/bff-proxy";

/**
 * Catch-all BFF proxy for `/api/v1/*`.
 *
 * Forward every method to the configured internal FastAPI backend while
 * preserving the path, query string, body (including multipart boundaries) and
 * the middleware-injected Authorization header. The destination is always the
 * configured API_URL — never anything from the client.
 *
 * Existing `/api/auth/*` route handlers are unaffected: Next.js resolves
 * specific routes before catch-alls, and this catch-all only matches paths
 * under `/api/v1/`.
 */

const BODYLESS_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

async function handle(
  req: NextRequest,
  params: { path?: string[] },
  method: string
): Promise<Response> {
  const path = params?.path ?? [];
  const search = req.nextUrl?.search ?? "";
  // Read the raw body for mutating methods so multipart boundaries are passed
  // through verbatim to FastAPI without parsing or reconstruction.
  const body =
    BODYLESS_METHODS.has(method) || method === "DELETE" ? null : await req.arrayBuffer();

  try {
    return await proxyToBackend({
      pathSegments: path,
      search,
      method,
      headers: req.headers,
      body,
    });
  } catch (err) {
    const detail =
      err instanceof ProxyUpstreamError
        ? "Upstream service is unavailable. Please try again shortly."
        : "The request could not be forwarded. Please try again shortly.";
    return new Response(JSON.stringify({ detail }), {
      status: 502,
      headers: { "content-type": "application/json" },
    });
  }
}

function makeHandler(method: string) {
  return async (
    req: NextRequest,
    ctx: { params: Promise<{ path?: string[] }> | { path?: string[] } }
  ): Promise<Response> => {
    const resolved = await ctx.params;
    return handle(req, resolved ?? {}, method);
  };
}

export const GET = makeHandler("GET");
export const POST = makeHandler("POST");
export const PUT = makeHandler("PUT");
export const PATCH = makeHandler("PATCH");
export const DELETE = makeHandler("DELETE");
export const OPTIONS = makeHandler("OPTIONS");

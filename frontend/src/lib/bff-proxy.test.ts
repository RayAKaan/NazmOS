/**
 * @jest-environment node
 */
import {
  proxyToBackend,
  buildUpstreamUrl,
  normalizeApiUrl,
  ProxyUpstreamError,
} from "@/lib/bff-proxy";

async function readBody(res: Response): Promise<Uint8Array> {
  const buf = await res.arrayBuffer();
  return new Uint8Array(buf);
}

function jsonResponse(
  body: unknown,
  status: number,
  headers: Record<string, string> = {}
): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

describe("bff-proxy — buildUpstreamUrl", () => {
  it("targets the configured API_URL and never a client-supplied host", () => {
    expect(buildUpstreamUrl(["guest-audit"], "", "http://backend:8000")).toBe(
      "http://backend:8000/api/v1/guest-audit"
    );
    expect(
      buildUpstreamUrl(["guest-audit"], "?a=1&b=2", "https://internal/api")
    ).toBe("https://internal/api/api/v1/guest-audit?a=1&b=2");
  });

  it("percent-encodes path segments so a segment cannot inject into the URL", () => {
    // A pre-encoded "%2F" is percent-encoded again to "%252F" so the upstream
    // never decodes it into a path separator — no traversal is possible.
    const url = buildUpstreamUrl(["x", "..%2F..%2Fetc", "a b"], "", "http://backend:8000");
    expect(url).toBe(
      "http://backend:8000/api/v1/x/..%252F..%252Fetc/a%20b"
    );
    expect(url).not.toContain("/etc");
  });

  it("rejects non-HTTP(S) API URLs", () => {
    expect(() => normalizeApiUrl("file:///etc/passwd").toString()).toThrow();
    expect(() => normalizeApiUrl("javascript:alert(1)")).toThrow();
  });

  it("adds the leading ? to a bare query string", () => {
    expect(buildUpstreamUrl(["guest-audit"], "rows=1", "http://b:8000")).toBe(
      "http://b:8000/api/v1/guest-audit?rows=1"
    );
  });
});

describe("bff-proxy — proxyToBackend", () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("forwards multipart body and content-type boundary to FastAPI", async () => {
    const boundary = "----WebKitFormBoundaryAbC123";
    const multipartBody = new TextEncoder().encode(
      `--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="sales.csv"\r\n\r\nsku,qty\r\nA,5\r\n--${boundary}--\r\n`
    );

    let capturedUrl = "";
    let capturedHeaders: Headers = new Headers();
    let capturedBody: BodyInit | null = null;
    global.fetch = jest.fn(async (url: any, init: any) => {
      capturedUrl = String(url);
      capturedHeaders = new Headers(init.headers);
      capturedBody = init.body;
      return jsonResponse({ summary: {} }, 200);
    }) as unknown as typeof fetch;

    await proxyToBackend({
      pathSegments: ["guest-audit"],
      method: "POST",
      headers: new Headers({
        "content-type": `multipart/form-data; boundary=${boundary}`,
        "accept": "application/json",
      }),
      body: multipartBody,
      apiUrl: "http://backend:8000",
    });

    expect(capturedUrl).toBe("http://backend:8000/api/v1/guest-audit");
    expect(capturedHeaders.get("content-type")).toBe(
      `multipart/form-data; boundary=${boundary}`
    );
    expect(capturedBody).toBe(multipartBody);
  });

  it("preserves backend status and allows binary bodies through unchanged", async () => {
    global.fetch = jest.fn(async () =>
      new Response(new Uint8Array([1, 2, 3]), { status: 413 })
    ) as unknown as typeof fetch;

    const res = await proxyToBackend({
      pathSegments: ["guest-audit"],
      method: "POST",
      apiUrl: "http://backend:8000",
    });

    expect(res.status).toBe(413);
    expect(Array.from(await readBody(res))).toEqual([1, 2, 3]);
  });

  it("preserves 4xx/5xx status and the backend detail string", async () => {
    global.fetch = jest.fn(async () =>
      jsonResponse({ detail: "No recognizable header row found." }, 422)
    ) as unknown as typeof fetch;

    const res = await proxyToBackend({
      pathSegments: ["guest-audit"],
      method: "POST",
      apiUrl: "http://backend:8000",
    });

    expect(res.status).toBe(422);
    const body = await res.json();
    expect(body.detail).toBe("No recognizable header row found.");
  });

  it("relays X-Guest-Session-Id back to the browser", async () => {
    global.fetch = jest.fn(async () =>
      jsonResponse({ summary: {} }, 200, { "x-guest-session-id": "sess-abc" })
    ) as unknown as typeof fetch;

    const res = await proxyToBackend({
      pathSegments: ["guest-audit"],
      method: "POST",
      apiUrl: "http://backend:8000",
    });

    expect(res.headers.get("x-guest-session-id")).toBe("sess-abc");
  });

  it("preserves query parameters through proxying", async () => {
    global.fetch = jest.fn(async () => jsonResponse({}, 200)) as unknown as typeof fetch;
    let capturedUrl = "";
    global.fetch = jest.fn(async (url: any) => {
      capturedUrl = String(url);
      return jsonResponse({}, 200);
    }) as unknown as typeof fetch;

    await proxyToBackend({
      pathSegments: ["guest-audit"],
      search: "page=2&limit=10",
      method: "GET",
      apiUrl: "http://backend:8000",
    });

    expect(capturedUrl).toBe(
      "http://backend:8000/api/v1/guest-audit?page=2&limit=10"
    );
  });

  it("forwards an Authorization header when present", async () => {
    let capturedHeaders: Headers = new Headers();
    global.fetch = jest.fn(async (_url: any, init: any) => {
      capturedHeaders = new Headers(init.headers);
      return jsonResponse({}, 200);
    }) as unknown as typeof fetch;

    await proxyToBackend({
      pathSegments: ["me"],
      method: "GET",
      headers: new Headers({ authorization: "Bearer jwt-abc" }),
      apiUrl: "http://backend:8000",
    });

    expect(capturedHeaders.get("authorization")).toBe("Bearer jwt-abc");
  });

  it("never forwards sensitive/credential headers or cookies to the backend", async () => {
    let capturedHeaders: Headers = new Headers();
    global.fetch = jest.fn(async (_url: any, init: any) => {
      capturedHeaders = new Headers(init.headers);
      return jsonResponse({}, 200);
    }) as unknown as typeof fetch;

    await proxyToBackend({
      pathSegments: ["guest-audit"],
      method: "POST",
      headers: new Headers({
        "cookie": "session=secret; access=garbage",
        "x-api-key": "super-secret-key",
        "x-backend-secret": "top-secret",
        "x-forwarded-for": "1.2.3.4",
        "content-type": "application/json",
      }),
      apiUrl: "http://backend:8000",
    });

    expect(capturedHeaders.has("cookie")).toBe(false);
    expect(capturedHeaders.has("x-api-key")).toBe(false);
    expect(capturedHeaders.has("x-backend-secret")).toBe(false);
    expect(capturedHeaders.has("content-type")).toBe(true);
  });

  it("does not leak backend credential or internal response headers to the browser", async () => {
    const backendResp = new Response(JSON.stringify({}), {
      status: 200,
      headers: {
        "content-type": "application/json",
        "x-guest-session-id": "sess-ok",
        "x-backend-token": "internal-secret",
        "set-cookie": "auth=secret",
        "x-powered-by": "FastAPI",
        "x-nextjs-internal": "leak-me",
      },
    });
    global.fetch = jest.fn(async () => backendResp) as unknown as typeof fetch;

    const res = await proxyToBackend({
      pathSegments: ["guest-audit"],
      method: "POST",
      apiUrl: "http://backend:8000",
    });

    expect(res.headers.get("x-backend-token")).toBeNull();
    expect(res.headers.get("set-cookie")).toBeNull();
    expect(res.headers.get("x-powered-by")).toBeNull();
    expect(res.headers.get("x-nextjs-internal")).toBeNull();
    expect(res.headers.get("content-type")).toBe("application/json");
    expect(res.headers.get("x-guest-session-id")).toBe("sess-ok");
  });

  it("throws ProxyUpstreamError with a safe message when the backend is unreachable", async () => {
    global.fetch = jest.fn(async () => {
      throw new TypeError("fetch failed");
    }) as unknown as typeof fetch;

    await expect(
      proxyToBackend({ pathSegments: ["guest-audit"], method: "POST", apiUrl: "http://backend:8000" })
    ).rejects.toBeInstanceOf(ProxyUpstreamError);
  });

  it("passes malformed / non-JSON backend responses through without crashing", async () => {
    const html = "<html><body>Bad Gateway</body></html>";
    global.fetch = jest.fn(
      async () => new Response(html, { status: 502, headers: { "content-type": "text/html" } })
    ) as unknown as typeof fetch;

    const res = await proxyToBackend({
      pathSegments: ["guest-audit"],
      method: "POST",
      apiUrl: "http://backend:8000",
    });

    expect(res.status).toBe(502);
    expect(res.headers.get("content-type")).toBe("text/html");
    expect(new TextDecoder().decode(await readBody(res))).toBe(html);
  });
});

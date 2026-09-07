import {
  extractGuestAuditError,
  sanitizeErrorMessage,
  guestAuditGenericError,
} from "@/lib/guest-audit-error";

const FALLBACK = guestAuditGenericError();

function axiosError(detail: unknown): unknown {
  return { response: { data: { detail } } };
}

describe("extractGuestAuditError", () => {
  it("returns a backend string detail verbatim (nicely cleaned)", () => {
    expect(extractGuestAuditError(axiosError("No recognizable header row found."))).toBe(
      "No recognizable header row found."
    );
  });

  it("never exposes credentials embedded in a detail string", () => {
    const msg = extractGuestAuditError(
      axiosError("Access denied with Bearer eyJhbGciOiJIUzI1NiJ9.sig.api_key=sk-12345")
    );
    expect(msg).not.toMatch(/sk-12345/);
    expect(msg).not.toMatch(/eyJhbGci/);
    expect(msg).toMatch(/Access denied/);
  });

  it("handles FastAPI 422 validation arrays (detail is a list)", () => {
    const err = {
      response: {
        data: {
          detail: [
            { loc: ["body", "file"], msg: "field required", type: "value_error.missing" },
          ],
        },
      },
    };
    expect(extractGuestAuditError(err)).toBe("field required");
  });

  it("handles JSON error objects with msg/message", () => {
    expect(extractGuestAuditError({ response: { data: { msg: "Too many files" } } })).toBe(
      "Too many files"
    );
    expect(
      extractGuestAuditError({ response: { data: { message: "Bad upload" } } })
    ).toBe("Bad upload");
  });

  it("falls back for HTML / non-JSON responses", () => {
    expect(
      extractGuestAuditError({ response: { data: "<html><body>Not Found</body></html>" } })
    ).toBe(FALLBACK);
  });

  it("falls back for network failures with no response", () => {
    expect(extractGuestAuditError(new TypeError("Network Error"))).toBe(FALLBACK);
  });

  it("falls back for unexpected response structures", () => {
    expect(extractGuestAuditError({ response: { data: 42 } })).toBe(FALLBACK);
    expect(extractGuestAuditError({})).toBe(FALLBACK);
    expect(extractGuestAuditError(null)).toBe(FALLBACK);
    expect(extractGuestAuditError(undefined)).toBe(FALLBACK);
  });

  it("strips stack-trace / internal-path noise from a detail string", () => {
    const msg = extractGuestAuditError(
      axiosError("boom\n    at getRow (/app/backend/app/services/x.py:42)\nprocess.env.API_KEY")
    );
    expect(msg).toBe(FALLBACK);
  });

  it("collapses whitespace and caps message length", () => {
    const long = "a ".repeat(1000);
    const msg = extractGuestAuditError(axiosError(long));
    expect(msg.length).toBeLessThanOrEqual(300);
    expect(msg).not.toMatch(/\s{2,}/);
  });
});

describe("sanitizeErrorMessage", () => {
  it("redacts bearer tokens, api keys and JWTs", () => {
    const out = sanitizeErrorMessage(
      "Bearer abc123 secret=xyz jwt eyJhbGciOiJIUzI1NiJ9 api_key=sk-live-99"
    );
    expect(out).not.toMatch(/abc123/);
    expect(out).not.toMatch(/xyz/);
    expect(out).not.toMatch(/eyJhbGci/);
    expect(out).not.toMatch(/sk-live-99/);
  });
});

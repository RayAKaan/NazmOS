/**
 * Safe extraction of a user-facing error message from an axios failure.
 *
 * Handles string `detail`, FastAPI 422 validation arrays, JSON error objects,
 * HTML/non-JSON responses, network failures and unexpected shapes — without ever
 * surfacing stack traces, internal paths, SQL, credentials or other sensitive
 * backend details.
 */

const DEFAULT_GUEST_AUDIT_ERROR =
  "Could not run the free audit. Try different files.";

/** Redact obvious secrets and collapse messy content into a single safe line. */
export function sanitizeErrorMessage(message: string): string {
  return message
    .replace(/\bBearer\s+[A-Za-z0-9._~+/=-]+/gi, "[redacted]")
    .replace(/\b(api[_-]?key|secret|token|password|passwd)\s*[:=]\s*\S+/gi, "$1 [redacted]")
    .replace(/\beyJ[A-Za-z0-9._-]+\b/g, "[redacted]")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 300);
}

/** True when a fragment looks like stack trace / internal path noise. */
function looksLikeInternalDetail(text: string): boolean {
  return /(\bat\s+[\w$]+\s*\(|node_modules|process\.env\.|\$\{[A-Z_]+\})/.test(text);
}

function firstUsefulString(values: unknown[]): string | null {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return null;
}

/**
 * Extract a safe, user-facing message from an unknown thrown value.
 * Falls back to {@link DEFAULT_GUEST_AUDIT_ERROR} for genuinely unknown cases.
 */
export function extractGuestAuditError(err: unknown, fallback = DEFAULT_GUEST_AUDIT_ERROR): string {
  const axiosError = err as { response?: { data?: { detail?: unknown } } };
  const detail = axiosError?.response?.data?.detail;

  let raw: string | null = null;

  if (typeof detail === "string") {
    raw = detail.trim();
  } else if (Array.isArray(detail)) {
    // FastAPI 422 validation errors: [{ loc, msg, type }]
    const first = detail.find((entry): entry is { msg?: unknown } => !!entry && typeof entry === "object");
    raw = firstUsefulString([first?.msg]);
  } else if (detail && typeof detail === "object") {
    const obj = detail as Record<string, unknown>;
    raw = firstUsefulString([obj.detail, obj.msg, obj.message]);
  } else {
    // `detail` was missing or non-object; inspect the response body itself for a
    // human-readable error field (msg/message/detail/error).
    const body = (err as { response?: { data?: unknown } })?.response?.data;
    if (body && typeof body === "object") {
      const obj = body as Record<string, unknown>;
      raw = firstUsefulString([obj.detail, obj.msg, obj.message, obj.error]);
    }
  }

  if (raw && !looksLikeInternalDetail(raw)) {
    const cleaned = sanitizeErrorMessage(raw);
    if (cleaned) {
      return cleaned;
    }
  }

  return fallback;
}

/** The generic fallback string, exposed for reuse in the UI. */
export function guestAuditGenericError(): string {
  return DEFAULT_GUEST_AUDIT_ERROR;
}

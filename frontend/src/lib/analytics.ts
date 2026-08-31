// Lightweight, zero-dependency analytics helper.
//
// Privacy-safe by design: events are written to the browser console only (a structured
// console.table per event) — no network requests, no cookies, no third parties, and no
// personally-identifiable data is ever collected. It exists so product decisions (which
// CTAs get clicked, which sections are seen) can be observed during development and demo
// without shipping a tracking dependency.
//
// Guarded behind a feature flag & environment check so it is inert in production unless
// explicitly enabled, and behind battery/respectable behavior (no infinite loops).
declare global {
  interface Window {
    __NAZMOS_ANALYTICS__?: boolean;
  }
}

const isEnabled = (): boolean =>
  typeof window !== "undefined" &&
  (window.__NAZMOS_ANALYTICS__ === true ||
    (process.env.NODE_ENV === "development" && localStorage.getItem("nazmos-analytics") === "on"));

export interface AnalyticsEvent {
  name: string;
  props?: Record<string, string | number | boolean | null | undefined>;
}

export function track(event: string, props?: AnalyticsEvent["props"]) {
  if (!isEnabled()) return;

  const payload: AnalyticsEvent = { name: event, props };
  // A single consolidated line so it is greppable and doesn't spam a fresh console.
  console.info(
    `[analytics] ${event}`,
    props && Object.keys(props).length ? props : "(no props)"
  );

  try {
    // Keep a bounded in-memory log for debugging session-level sequencing.
    const log = (window.__NAZMOS_ANALYTICS_LOG__ ||= []);
    log.push({ ts: Date.now(), ...payload });
    if (log.length > 500) log.shift();
  } catch {
    /* ignore */
  }
}

declare global {
  interface Window {
    __NAZMOS_ANALYTICS_LOG__?: (AnalyticsEvent & { ts: number })[];
  }
}

export { };

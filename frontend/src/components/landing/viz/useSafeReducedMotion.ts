"use client";

import { useEffect, useState } from "react";

/**
 * SSR-safe prefers-reduced-motion hook.
 *
 * framer-motion's `useReducedMotion` reads `prefers-reduced-motion` synchronously
 * on first render, so on the server it returns `false` but on the client's first
 * render under `prefers-reduced-motion: reduce` it returns `true`. Any layout that
 * branches on that value then differs between server HTML and the hydration tree,
 * producing a React hydration-mismatch (with the SSR subtree discarded).
 *
 * This hook starts at `false` on both server and first client render (identical to
 * the SSR HTML) and synchronises to the real OS preference only after hydration in
 * an effect. Reduced-motion behaviour is preserved without breaking hydration.
 */
export function useSafeReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  return reduced;
}

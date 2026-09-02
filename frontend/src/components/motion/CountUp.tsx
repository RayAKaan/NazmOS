"use client";

import { useInView, useSpring, useTransform, motion } from "framer-motion";
import { useRef, useEffect, useState } from "react";
import { cn } from "@/lib/utils";

/**
 * CountUp — an animated numeric counter.
 *
 * Counts from `from` to `to` when scrolled into view, using a spring for
 * a smooth, non-jittering feel (uses requestAnimationFrame internally).
 * Formats via an optional formatter (default: localized integer).
 * Respects reduced-motion by rendering the final value immediately.
 */
export function CountUp({
  to,
  from = 0,
  duration = 1.6,
  formatter,
  className,
  prefix = "",
  suffix = "",
}: {
  to: number;
  from?: number;
  duration?: number;
  formatter?: (n: number) => string;
  className?: string;
  prefix?: string;
  suffix?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "-40px" });
  const [value, setValue] = useState(from);

  const spring = useSpring(from, { duration });

  useEffect(() => {
    if (inView) {
      spring.set(to);
      const unsub = spring.on("change", (v) => setValue(v));
      return unsub;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inView, to]);

  const reduce = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const display = reduce ? to : value;

  return (
    <span ref={ref} className={cn("tabular-nums", className)}>
      {prefix}
      {formatter ? formatter(display) : Math.round(display).toLocaleString()}
      {suffix}
    </span>
  );
}

import { cn } from "@/lib/utils";
import { weaveAccent, WEAVE_FIELD_MASK_URL } from "./weave";

/**
 * §3 WeaveTile — Gulf shemagh hook motif, abstracted, capped at ~5% surface coverage.
 *
 * - variant="field"  → full-bleed background. Rendered as a CSS `background-color` +
 *   mask-image data-URI (NOT a DOM grid of `<use>` — see §6). Colour comes from
 *   `--weave-accent` / `--weave-accent-teal`; opacity from `--weave-opacity-bg`
 *   (0.03–0.05 dark, 40% of that in light — §2.5).
 * - variant="chevron"→ the 12px zigzag tile used ONLY by ChevronDivider (never mixed
 *   into the field). Uses `<use href="#weave-chevron">` from WeaveSprite.
 *
 * Usage:
 *   <div className="relative"><WeaveTile variant="field" /><p>copy</p></div>
 *   <WeaveTile variant="chevron" color="teal" />
 */
export type WeaveTileProps = {
  variant: "field" | "chevron";
  color?: "gold" | "teal";
  /** overrides --weave-opacity-bg; only meaningful for variant="field". */
  opacity?: number;
  /** px tile size — defaults 24 (field) / 12 (chevron). */
  size?: number;
  className?: string;
};

export function WeaveTile({
  variant,
  color = "gold",
  opacity,
  size,
  className,
}: WeaveTileProps) {
  const accent = weaveAccent(color);

  if (variant === "field") {
    const tile = size ?? 24;
    return (
      <div
        aria-hidden="true"
        className={cn("pointer-events-none absolute inset-0", className)}
        style={{
          backgroundColor: accent,
          WebkitMaskImage: WEAVE_FIELD_MASK_URL,
          maskImage: WEAVE_FIELD_MASK_URL,
          WebkitMaskRepeat: "repeat",
          maskRepeat: "repeat",
          WebkitMaskSize: `${tile}px ${tile * 2}px`,
          maskSize: `${tile}px ${tile * 2}px`,
          opacity: opacity ?? "var(--weave-opacity-bg)",
        }}
      />
    );
  }

  // chevron — full accent opacity (no transparency: at small scale low opacity vanishes, §3).
  const tile = size ?? 12;
  return (
    <div
      aria-hidden="true"
      className={cn("pointer-events-none flex items-center overflow-hidden", className)}
      style={{ color: accent, height: tile, width: tile }}
    >
      <svg
        width={tile}
        height={tile}
        viewBox="0 0 12 12"
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
      >
        <use href="#weave-chevron" />
      </svg>
    </div>
  );
}

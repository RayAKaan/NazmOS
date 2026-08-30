import { cn } from "@/lib/utils";
import { weaveAccent, WEAVE_CHEVRON_MASK_URL } from "./weave";

/**
 * ChevronDivider — the §3 chevron border tile (12px zigzag, 2px stroke), used ONLY as a
 * section divider. Direction-agnostic geometry → RTL-safe (§7).
 *
 * Usage:
 *   <ChevronDivider />                          // horizontal rule between sections
 *   <ChevronDivider orientation="vertical" />   // in a flex row, spans full height
 */
export type ChevronDividerProps = {
  orientation?: "horizontal" | "vertical";
  className?: string;
};

export function ChevronDivider({ orientation = "horizontal", className }: ChevronDividerProps) {
  const isH = orientation === "horizontal";
  return (
    <div
      aria-hidden="true"
      className={cn(
        "pointer-events-none",
        isH ? "h-3 w-full" : "w-3 self-stretch",
        className
      )}
      style={{
        backgroundColor: weaveAccent("gold"),
        WebkitMaskImage: WEAVE_CHEVRON_MASK_URL,
        maskImage: WEAVE_CHEVRON_MASK_URL,
        WebkitMaskRepeat: isH ? "repeat-x" : "repeat-y",
        maskRepeat: isH ? "repeat-x" : "repeat-y",
        WebkitMaskSize: "12px 12px",
        maskSize: "12px 12px",
      }}
    />
  );
}

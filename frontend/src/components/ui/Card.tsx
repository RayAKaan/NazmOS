import { HTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/utils";
import { WeaveTile } from "./WeaveTile";

/**
 * Card — reworked per §4.
 * density  "editorial" → p-8 (32px) desktop KPI/editorial cards · "data" → p-4 (16px) dense tables.
 * trim     "weave"     → WeaveTile variant="field" top-edge strip at FULL accent opacity
 *                        (dashboard KPI cards only, §3).
 * variant  "default" (bg-card + border-border) | "bordered" (stronger input border).
 *
 * Usage:
 *   <Card density="editorial" trim="weave" hoverable>…</Card>
 *   <Card density="data">…</Card>
 */
export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  density?: "editorial" | "data";
  trim?: "none" | "weave";
  variant?: "default" | "bordered";
  hoverable?: boolean;
}

export const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ className, density = "editorial", trim = "none", variant = "default", hoverable = false, children, ...props }, ref) => {
    // §A elevation: level-1 (standard/data) · level-2 (KPI/hero = trim="weave").
    // level-2 also lifts -2px and brightens the border toward gold on hover.
    const elevated = trim === "weave";
    return (
      <div
        ref={ref}
        className={cn(
          "overflow-hidden rounded-lg border bg-card",
          variant === "bordered" ? "border-input" : "border-border",
          elevated
            ? "shadow-elevation-2 transition-[transform,border-color,box-shadow] duration-150 ease-out hover:-translate-y-0.5 hover:border-border/30"
            : "shadow-elevation-1",
          hoverable && "transition-colors duration-200 hover:bg-surface-hover",
          className
        )}
        {...props}
      >
        {trim === "weave" && (
          <div className="relative h-6 w-full">
            <WeaveTile variant="field" opacity={1} />
          </div>
        )}
        <div className={density === "editorial" ? "p-8" : "p-4"}>{children}</div>
      </div>
    );
  }
);

Card.displayName = "Card";

/* Back-compat subcomponents — padding now belongs to Card `density`; these are bare slots. */
export function CardHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("border-b border-border", className)} {...props} />;
}

export function CardTitle({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn("font-sans text-lg font-medium text-foreground", className)} {...props} />;
}

export function CardDescription({ className, ...props }: HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("mt-1 text-sm text-muted-foreground", className)} {...props} />;
}

export function CardContent({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={className} {...props} />;
}

export function CardFooter({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex items-center gap-2", className)} {...props} />;
}

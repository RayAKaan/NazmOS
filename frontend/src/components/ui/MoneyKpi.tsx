import { cn } from "@/lib/utils";

// Money hierarchy primitive (B1). Large serif money figure per the money-psychology
// design language. Tones map to canonical tokens; "destructive"/"warning" tones are
// required by the design-system/destructive-needs-action rule to live next to an
// action (button/a/onClick/href) in the calling component.
type Tone = "default" | "gold" | "teal" | "success" | "destructive" | "warning";

const toneClass: Record<Tone, string> = {
  default: "text-foreground",
  gold: "text-primary",
  teal: "text-secondary",
  success: "text-success",
  destructive: "text-destructive",
  warning: "text-warning",
};

export function MoneyKpi({
  value,
  tone = "default",
  label,
  currency = "SAR",
  className,
}: {
  value: number | string;
  tone?: Tone;
  label?: string;
  currency?: string;
  className?: string;
}) {
  const formatted =
    typeof value === "number"
      ? value.toLocaleString("en-US", { maximumFractionDigits: 2 })
      : value;

  return (
    <div className={cn("flex flex-col", className)}>
      {label && <span className="text-xs text-muted-foreground mb-1.5">{label}</span>}
      <span
        className={cn(
          "font-serif font-black text-4xl md:text-5xl tracking-tight tabular-nums",
          toneClass[tone]
        )}
      >
        {currency} {formatted}
      </span>
    </div>
  );
}

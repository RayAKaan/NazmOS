import { Loader2 } from "lucide-react";
import { SkeletonCard, SkeletonChart, SkeletonTable } from "@/components/ui/Skeleton";
import { cn } from "@/lib/utils";

type LoadingVariant = "spinner" | "cards" | "table" | "chart";

interface LoadingStateProps {
  label?: string;
  variant?: LoadingVariant;
  className?: string;
}

export function LoadingState({
  label = "Loading…",
  variant = "cards",
  className,
}: LoadingStateProps) {
  if (variant === "spinner") {
    return (
      <div
        role="status"
        aria-label={label}
        className={cn("flex flex-col items-center justify-center gap-3 py-16", className)}
      >
        <Loader2 className="h-8 w-8 animate-spin text-brand-amber" aria-hidden />
        <p className="text-sm text-muted-foreground">{label}</p>
      </div>
    );
  }

  return (
    <div role="status" aria-label={label} className={cn("space-y-6", className)}>
      <p className="sr-only">{label}</p>
      {variant === "cards" && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      )}
      {variant === "table" && <SkeletonTable rows={6} />}
      {variant === "chart" && <SkeletonChart />}
    </div>
  );
}

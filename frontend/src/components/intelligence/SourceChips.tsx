"use client";

import { cn } from "@/lib/utils";

interface SourceChipsProps {
  sources: string[];
  max?: number;
  className?: string;
}

export function SourceChips({ sources, max = 4, className }: SourceChipsProps) {
  if (!sources || sources.length === 0) return null;

  const visible = sources.slice(0, max);
  const remaining = sources.length - max;

  return (
    <div className={cn("flex flex-wrap gap-1.5", className)}>
      {visible.map((source) => (
        <span
          key={source}
          className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-brand-cream/5 text-muted-foreground border border-brand-cream/5"
        >
          {source}
        </span>
      ))}
      {remaining > 0 && (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-brand-cream/5 text-muted-foreground border border-brand-cream/5">
          +{remaining}
        </span>
      )}
    </div>
  );
}

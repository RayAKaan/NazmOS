"use client";

import { cn } from "@/lib/utils";
import type { NodeType } from "./types";

const TONES: Record<NodeType, string> = {
  product: "text-secondary border-border/30 bg-secondary/10",
  branch: "text-secondary border-border/25 bg-secondary/[0.08]",
  supplier: "text-muted-foreground border-border bg-muted/30",
  inventory: "text-foreground border-border bg-card",
  sales: "text-foreground border-border bg-card",
  margin: "text-warning border-warning/30 bg-warning/10",
  finding: "text-destructive border-destructive/30 bg-destructive/10",
  decision: "text-primary border-border/30 bg-primary/10",
  action: "text-success border-success/30 bg-success/10",
  outcome: "text-success border-success/30 bg-success/10",
};

const DOTS: Partial<Record<NodeType, string>> = {
  product: "bg-secondary",
  branch: "bg-secondary",
  finding: "bg-destructive",
  decision: "bg-primary",
  action: "bg-success",
  outcome: "bg-success",
};

/**
 * NodeChip — a data-driven graph node rendered as an HTML chip (not raw SVG text),
 * so label wrapping, RTL and long Arabic captions stay readable and accessible.
 * Placed by the layout layer over an SVG relationship canvas.
 */
export function NodeChip({
  node,
  active,
  muted,
  onClick,
  className,
}: {
  node: { id: string; type: NodeType; label: string; caption?: string };
  active?: boolean;
  muted?: boolean;
  onClick?: () => void;
  className?: string;
}) {
  const dot = DOTS[node.type];
  const inner = (
    <>
      <span className="flex items-center gap-1.5 text-[13px] font-semibold leading-tight">
        {dot && <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", dot)} aria-hidden="true" />}
        <span>{node.label}</span>
      </span>
      {node.caption && (
        <span className="mt-0.5 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
          {node.caption}
        </span>
      )}
    </>
  );
  const base = cn(
    "group flex flex-col items-start rounded-lg border px-3 py-2 text-left transition-all",
    TONES[node.type],
    muted && "opacity-40",
    className
  );
  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        aria-pressed={active}
        className={cn(base, "cursor-pointer hover:-translate-y-0.5 focus-visible:outline-2 focus-visible:outline-ring")}
      >
        {inner}
      </button>
    );
  }
  return <div className={base}>{inner}</div>;
}

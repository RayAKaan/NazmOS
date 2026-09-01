"use client";

import { useId, useState } from "react";
import { cn } from "@/lib/utils";
import { NodeChip } from "./NodeChip";
import { FlowLine } from "./FlowLine";
import type { GraphNode, GraphEdge } from "./types";

/**
 * GraphDiagram — a readable, sparse, relationship graph (§10).
 *
 * Nodes are laid out on a responsive percentage grid ("col", "row") and rendered as
 * accessible HTML chips; edges are drawn as animated SVG relationship lines behind
 * them with semantic labels. Hovering/selecting a node highlights its connected
 * edges and dims unrelated ones.
 *
 * Responsive (§9): a full 6-column graph does not fit narrow phones (chips would
 * overlap / bleed past the container), so below `sm` it collapses to a compact,
 * non-absolute "relationship list" that can never overflow — the same data, read
 * vertically. This also keeps the layout stable in RTL.
 */
export function GraphDiagram({
  nodes,
  edges,
  className,
  interactive = true,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  className?: string;
  interactive?: boolean;
}) {
  const arrowId = useId();
  const [selected, setSelected] = useState<string | null>(null);

  // Explicit, deliberate layout (col 0..5, row 0..3) over an ~6x4 grid.
  const POS: Record<string, { col: number; row: number }> = {
    arabica: { col: 0, row: 0 },
    riyadh: { col: 2, row: 0 },
    jeddah: { col: 4, row: 0 },
    roaster: { col: 1, row: 2 },
    stock: { col: 2, row: 2 },
    sales: { col: 3, row: 2 },
    margin: { col: 5, row: 2 },
    finding: { col: 2, row: 3 },
    decision: { col: 3, row: 3 },
    outcome: { col: 4, row: 3 },
  };

  const pos = (id: string) => POS[id] ?? { col: 0, row: 0 };
  const nCols = 6;
  const nRows = 4;

  // Build the SVG relationship lines via normalized coordinates.
  const toUnit = (c: number, r: number) => ({
    x: (c + 0.5) / nCols,
    y: (r + 0.5) / nRows,
  });

  const edgesFor = (id: string) =>
    edges.filter((e) => e.source === id || e.target === id);

  return (
    <div className={cn("relative", className)}>
      {/* Desktop / tablet: full relationship graph. */}
      <div className="hidden h-full w-full sm:block">
        <svg
          className="pointer-events-none absolute inset-0 h-full w-full"
          viewBox="0 0 600 400"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <defs>
            <marker
              id={arrowId}
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="5"
              markerHeight="5"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" />
            </marker>
          </defs>
          {edges.map((e) => {
            const a = toUnit(pos(e.source).col, pos(e.source).row);
            const b = toUnit(pos(e.target).col, pos(e.target).row);
            // Slight vertical curve for organic feel. Round to fixed precision so
            // server and client render identical DOM (SSR hydration stability).
            const r = (n: number) => Math.round(n * 1000) / 1000;
            const midY = r((a.y + b.y) / 2 - 0.03);
            const d = `M ${r(a.x * 600)} ${r(a.y * 400)} Q ${r(((a.x + b.x) / 2) * 600)} ${r(midY * 400)} ${r(b.x * 600)} ${r(b.y * 400)}`;
            const active = selected ? selected === e.source || selected === e.target : true;
            const cx = r(((a.x + b.x) / 2) * 600);
            const cy = r(midY * 400);
            return (
              <g
                key={`${e.source}-${e.target}`}
                className={cn("transition-opacity duration-300", active ? "opacity-100" : "opacity-25")}
              >
                <FlowLine d={d} strokeWidth={1.2} duration={2.2} />
                <g className="text-muted-foreground/70">
                  <circle r={2} fill="currentColor" cx={cx} cy={cy} />
                  <text
                    x={cx}
                    y={cy - 6}
                    textAnchor="middle"
                    fontSize="9"
                    fill="currentColor"
                    className="font-mono uppercase"
                    style={{ letterSpacing: "0.06em" }}
                  >
                    {e.relationship.replace(/_/g, " ")}
                  </text>
                </g>
              </g>
            );
          })}
        </svg>

        {/* Node chips overlaid on the percentage grid */}
        {nodes.map((n) => {
          const p = pos(n.id);
          const isConnected = selected ? edgesFor(selected).some((e) => e.source === n.id || e.target === n.id) : true;
          const isSelf = selected === n.id;
          return (
            <div
              key={n.id}
              className="absolute -translate-x-1/2 -translate-y-1/2"
              style={{ left: `${((p.col + 0.5) / nCols) * 100}%`, top: `${((p.row + 0.5) / nRows) * 100}%` }}
            >
              <NodeChip
                node={n}
                active={isSelf}
                muted={interactive && selected !== null && !isConnected}
                onClick={interactive ? () => setSelected(isSelf ? null : n.id) : undefined}
              />
            </div>
          );
        })}
      </div>

      {/* Mobile: compact relationship list (can never overflow, RTL-safe). */}
      <ul className="space-y-2.5 sm:hidden">
        {edges.slice(0, 6).map((e, i) => {
          const s = nodes.find((n) => n.id === e.source);
          const t = nodes.find((n) => n.id === e.target);
          if (!s || !t) return null;
          return (
            <li key={`${e.source}-${e.target}-${i}`}>
              <div className="flex items-center gap-2 rounded-xl border border-border bg-card px-3 py-2 text-left">
                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-primary" aria-hidden="true" />
                <span className="min-w-0 flex-1 truncate text-sm font-semibold text-foreground">
                  {s.label} <span className="text-primary/70">→</span> {t.label}
                </span>
                <span className="shrink-0 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                  {e.relationship.replace(/_/g, " ")}
                </span>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

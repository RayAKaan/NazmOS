"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

/**
 * BusinessGraph — a knowledge graph composed of real business entities.
 *
 * Nodes: PRODUCT, SALES, STOCK, SUPPLIER, COST, MARGIN, DEMAND.
 * Hovering/selecting a node highlights its direct relationships and dims
 * the rest. Below `sm` it collapses to a vertical relationship list (the
 * desktop network cannot scale down legibly).
 *
 * This is a signature visual — it must communicate relationships, not an
 * abstract neural network.
 */
export function BusinessGraph() {
  const { t } = useI18n();
  const edges = t.nazmos.graphStory.edges;

  // Explicit layout on a normalized 100x60 space.
  const NODES = [
    { id: "product", label: "PRODUCT", x: 50, y: 8, tone: "ivory" },
    { id: "sales", label: edges.sales, x: 20, y: 30, tone: "teal" },
    { id: "stock", label: edges.stock, x: 47, y: 34, tone: "teal" },
    { id: "cost", label: edges.cost, x: 74, y: 30, tone: "teal" },
    { id: "supplier", label: edges.supplier, x: 8, y: 55, tone: "muted" },
    { id: "margin", label: edges.margin, x: 50, y: 52, tone: "muted" },
    { id: "demand", label: edges.demand, x: 90, y: 55, tone: "muted" },
  ] as const;

  const EDGES = [
    { s: "product", d: "sales" },
    { s: "product", d: "stock" },
    { s: "product", d: "cost" },
    { s: "supplier", d: "cost" },
    { s: "cost", d: "margin" },
    { s: "sales", d: "demand" },
    { s: "stock", d: "supplier" },
  ] as const;

  const [selected, setSelected] = useState<string | null>(null);

  const neighbors = (id: string | null) => {
    if (!id) return new Set<string>();
    const set = new Set<string>([id]);
    for (const e of EDGES) {
      if (e.s === id) set.add(e.d);
      if (e.d === id) set.add(e.s);
    }
    return set;
  };
  const active = neighbors(selected);

  return (
    <div className="w-full">
      {/* Desktop network */}
      <div className="relative hidden aspect-[4/3] w-full sm:block">
        {/* Edges */}
        <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 60" preserveAspectRatio="none" aria-hidden="true">
          {EDGES.map((e) => {
            const s = NODES.find((n) => n.id === e.s)!;
            const d = NODES.find((n) => n.id === e.d)!;
            const highlighted = selected ? active.has(e.s) && active.has(e.d) : true;
            return (
              <line
                key={`${e.s}-${e.d}`}
                x1={s.x} y1={s.y} x2={d.x} y2={d.y}
                stroke="var(--brand-teal)"
                strokeOpacity={highlighted ? 0.4 : 0.08}
                strokeWidth={highlighted ? 0.5 : 0.25}
              />
            );
          })}
        </svg>

        {/* Nodes */}
        {NODES.map((n) => {
          const isActive = !selected || active.has(n.id);
          const dimmed = selected && !isActive;
          return (
            <button
              key={n.id}
              type="button"
              onClick={() => setSelected(selected === n.id ? null : n.id)}
              onMouseEnter={() => setSelected(n.id)}
              className={cn(
                "absolute -translate-x-1/2 -translate-y-1/2 rounded-full border px-3 py-1.5 font-mono text-[10px] font-semibold uppercase tracking-wider transition-all focus-ring",
                n.tone === "ivory"
                  ? "border-border bg-card text-foreground shadow-subtle"
                  : n.tone === "teal"
                  ? "border-primary/40 bg-primary/10 text-foreground"
                  : "border-border bg-card/60 text-muted-foreground",
                dimmed && "opacity-30"
              )}
              style={{ left: `${n.x}%`, top: `${n.y}%`, zIndex: 2 }}
            >
              <span
                className={cn(
                  "mr-1.5 inline-block h-1.5 w-1.5 rounded-full",
                  n.tone === "teal" ? "bg-primary" : n.tone === "ivory" ? "bg-brand-gold" : "bg-muted-foreground"
                )}
                aria-hidden="true"
              />
              {n.label}
            </button>
          );
        })}
      </div>

      {/* Mobile: vertical relationship list */}
      <div className="sm:hidden">
        <NodeList items={NODES} edges={EDGES} />
      </div>
    </div>
  );
}

function NodeList({
  items,
  edges,
}: {
  items: readonly { id: string; label: string; tone: string }[];
  edges: readonly { s: string; d: string }[];
}) {
  const { t } = useI18n();
  return (
    <ul className="space-y-2" aria-label={t.nazmos.graphStory.title}>
      {items.map((n) => {
        const rels = edges
          .filter((e) => e.s === n.id)
          .map((e) => items.find((i) => i.id === e.d)?.label)
          .filter(Boolean);
        return (
          <li key={n.id} className="flex items-center justify-between gap-3 rounded-lg border border-border bg-card px-4 py-3">
            <span className="flex items-center gap-2 font-mono text-xs font-semibold uppercase tracking-wider text-foreground">
              <span
                className={cn(
                  "h-1.5 w-1.5 rounded-full",
                  n.tone === "teal" ? "bg-primary" : n.tone === "ivory" ? "bg-brand-gold" : "bg-muted-foreground"
                )}
                aria-hidden="true"
              />
              {n.label}
            </span>
            {rels.length > 0 && (
              <span className="text-[10px] text-muted-foreground">{rels.join(" · ")}</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

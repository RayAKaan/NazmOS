"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import {
  DOMAINS,
  EDGES,
  NODE_POS,
  computeEmphasis,
  edgeKey,
  mirrorX,
  type NodeId,
  type UniverseState,
} from "./data";

interface UniverseSceneProps {
  state: UniverseState;
  onSelect: (node: NodeId) => void;
  focusNode?: NodeId | null;
  compact?: boolean;
  className?: string;
}

const VEC = { x: 50, y: 50 };

function edgePath(a: NodeId, b: NodeId, rtl: boolean, level: number, converge: boolean): string {
  const pa = NODE_POS[a];
  const pb = NODE_POS[b];
  const x1 = mirrorX(pa.x, rtl);
  const y1 = pa.y;
  const x2 = mirrorX(pb.x, rtl);
  const y2 = pb.y;
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2;

  let cx: number;
  let cy: number;
  if (converge) {
    // Convergence state: every filament bows toward the centre — the system
    // physically gathers toward NazmOS instead of sitting in fixed positions.
    cx = mx + (VEC.x - mx) * 0.45;
    cy = my + (VEC.y - my) * 0.45;
  } else {
    const dx = x2 - x1;
    const dy = y2 - y1;
    const len = Math.hypot(dx, dy) || 1;
    const px = -dy / len;
    const py = dx / len;
    // Deterministic, stable filament direction per relationship pair.
    const k = edgeKey(a, b);
    let h = 7;
    for (let i = 0; i < k.length; i++) h = (h * 31 + k.charCodeAt(i)) >>> 0;
    const dir = h % 2 === 0 ? 1 : -1;
    const curve = 3 + level * 4;
    cx = mx + px * curve * dir;
    cy = my + py * curve * dir;
  }
  return `M ${x1} ${y1} Q ${cx} ${cy} ${x2} ${y2}`;
}

export function UniverseScene({ state, onSelect, focusNode, compact, className }: UniverseSceneProps) {
  const { t, dir } = useI18n();
  const rtl = dir === "rtl";

  // Hover is a non-destructive focus preview; it never drives the state machine.
  const [hovered, setHovered] = useState<NodeId | null>(null);

  const em = computeEmphasis(state, hovered);
  const dimmed = em.dimmed;
  const converging = state.kind === "nazmos";

  const nodeLevel = (id: NodeId): number => em.nodeLevels[id] ?? 0;
  const edgeLevel = (a: NodeId, b: NodeId): number => em.edgeLevels[edgeKey(a, b)] ?? 0;

  const isActiveNode = (id: NodeId) => state.kind === "domain" && state.domain === id;

  // Continuity: the network is dimmed (but never removed) behind panel states.
  // The company message rests on the most recessed network so it reads clearly.
  const sceneOpacity = compact
    ? 1
    : state.kind === "company"
      ? 0.4
      : dimmed
        ? 0.55
        : 1;

  const nodeButton = (id: NodeId, seq: number) => {
    const label =
      id === "audit" ? t.universe.audit.label : t.universe.nodes[id].label;
    const level = nodeLevel(id);
    const active = isActiveNode(id);
    const focused = focusNode === id;
    const pos = NODE_POS[id];
    const x = mirrorX(pos.x, rtl);
    const y = pos.y;
    const dotSize =
      converging && id === "nazmos"
        ? 16
        : level >= 2
          ? 14
          : level === 1
            ? 10
            : 8;

    return (
      <motion.button
        key={`node-${id}`}
        type="button"
        data-node={id}
        data-level={level}
        onClick={() => onSelect(id)}
        onMouseEnter={() => setHovered(id)}
        onMouseLeave={() => setHovered(null)}
        className="absolute -translate-x-1/2 -translate-y-1/2 rounded-full p-1.5 focus-ring"
        style={{ left: `${x}%`, top: `${y}%`, zIndex: level >= 2 ? 30 : 20 + seq }}
        aria-label={label}
        initial={false}
        animate={{ scale: active || focused ? 1.1 : 1, opacity: sceneOpacity }}
        transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
      >
        <span
          className={cn(
            "pointer-events-none flex flex-col items-center gap-1 whitespace-nowrap",
            compact && "gap-0.5",
          )}
        >
          <span
            className={cn(
              "relative grid shrink-0 place-items-center rounded-full transition-colors duration-300",
              level >= 2
                ? id === "nazmos"
                  ? "u-node-2 u-gold-glow"
                  : "u-node-2 u-teal-glow"
                : level === 1
                  ? "u-node-1"
                  : "u-node-0",
            )}
            style={{ width: dotSize, height: dotSize }}
          />
          <span
            className={cn(
              "font-mono font-medium uppercase tracking-[0.16em] transition-colors duration-300",
              compact ? "text-[9px]" : "text-[10px] md:text-[11px]",
              level >= 2 ? "u-ink" : level === 1 ? "u-ink-dim" : "u-ink-faint",
            )}
          >
            {label}
          </span>
        </span>
      </motion.button>
    );
  };

  return (
    <div className={cn("relative", className)}>
      <svg
        className="pointer-events-none absolute inset-0 h-full w-full"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        {EDGES.map((e) => {
          const level = edgeLevel(e.a, e.b);
          const d = edgePath(e.a, e.b, rtl, level, converging);
          // cost is the value face — its threads are gold filaments in both
          // modes, tying capital into the teal system (spec §35).
          const isValue = e.a === "cost" || e.b === "cost";
          return (
            <motion.path
              key={edgeKey(e.a, e.b)}
              d={d}
              vectorEffect="non-scaling-stroke"
              strokeWidth={level >= 2 ? 1.6 : level === 1 ? 1.1 : 0.9}
              fill="none"
              className={
                level >= 2
                  ? isValue
                    ? "u-edge-gold"
                    : "u-edge-2"
                  : isValue
                    ? "u-edge-gold"
                    : level === 1
                      ? "u-edge-1"
                      : "u-edge-0"
              }
              initial={false}
              animate={{ opacity: sceneOpacity }}
              transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
            />
          );
        })}
      </svg>

      {/* Nodes — real buttons: keyboard focusable, programmatically selectable. */}
      {(["nazmos", ...DOMAINS] as NodeId[]).map((id, i) => nodeButton(id, i))}
    </div>
  );
}
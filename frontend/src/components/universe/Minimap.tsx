"use client";

import { motion } from "framer-motion";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { DOMAINS, EDGES, NODE_POS, edgeKey, mirrorX, type NodeId, type UniverseState } from "./data";

interface UniverseMinimapProps {
  state: UniverseState;
  onSelect: (node: NodeId) => void;
}

/**
 * System compass — spatial orientation, not a dashboard widget (spec §23).
 *
 * A miniature universe: the same five-contentated lines and nodes the main
 * scene shows, compressed into the corner. It marks where you are and lets you
 * return to the universe; it deliberately does not enable node-to-node jumps
 * (see UniverseState).
 */
export function UniverseMinimap({ state, onSelect }: UniverseMinimapProps) {
  const { t, dir } = useI18n();
  const rtl = dir === "rtl";

  const active: NodeId | null =
    state.kind === "domain" ? (state.domain ?? null) : state.kind === "nazmos" ? "nazmos" : null;

  return (
    <div
      className="pointer-events-none absolute bottom-4 end-4 z-40 hidden select-none md:block"
      aria-label={t.universe.legend.label}
      role="group"
    >
      <svg viewBox="0 0 100 100" className="pointer-events-none block h-24 w-24" aria-hidden="true">
        {EDGES.map((e) => {
          const a = NODE_POS[e.a];
          const b = NODE_POS[e.b];
          const k = edgeKey(e.a, e.b);
          // cost-flavoured compass threads stay gold; the rest teal — the same
          // material language as the main scene, at miniature scale.
          const isValue = e.a === "cost" || e.b === "cost";
          return (
            <line
              key={k}
              x1={mirrorX(a.x, rtl)}
              y1={a.y}
              x2={mirrorX(b.x, rtl)}
              y2={b.y}
              className={isValue ? "u-edge-gold" : "u-edge-0"}
              strokeWidth="0.45"
              vectorEffect="non-scaling-stroke"
            />
          );
        })}

        {(["nazmos", ...DOMAINS] as NodeId[]).map((id) => {
          const pos = NODE_POS[id];
          const isActive = active === id;
          const isNazmos = id === "nazmos";
          return (
            <g key={`mm-${id}`} transform={`translate(${mirrorX(pos.x, rtl)} ${pos.y})`}>
              {isNazmos && (
                <circle r="4" fill="none" className="u-edge-gold" strokeWidth="0.5" vectorEffect="non-scaling-stroke" />
              )}
              <motion.circle
                r={isActive ? 1.7 : isNazmos ? 1.4 : 1.1}
                className={cn(
                  isActive ? "u-node-gold u-gold-glow" : isNazmos ? "u-node-2" : "u-node-0",
                )}
                initial={false}
                animate={{ opacity: isActive ? 1 : 0.75 }}
                transition={{ duration: 0.3 }}
              />
            </g>
          );
        })}

        {/* Live audit marker */}
        <circle
          cx={mirrorX(88, rtl)}
          cy="10"
          r="1.4"
          className={state.kind === "audit" ? "u-node-2" : "u-node-0"}
          style={{ opacity: state.kind === "audit" ? 1 : 0.45 }}
        />
      </svg>

      {/* Active node label, compass-style */}
      <p className="u-ink-faint mt-1 text-center font-mono text-[9px] uppercase tracking-[0.2em]">
        {active ? t.universe.nodes[active].label : t.universe.legend.label}
      </p>
      <span className="sr-only">{t.universe.legend.live}</span>
    </div>
  );
}
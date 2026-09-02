"use client";

import { motion } from "framer-motion";
import { useI18n } from "@/lib/i18n";
import { NazmakSection, NazmakHeader } from "./section";
import { EASE_STANDARD } from "@/components/motion/ScrollReveal";

/**
 * FutureScaleVisual — the "hidden layer" message.
 *
 * NazmOS is one visible node. As the visitor scrolls/interacts, the network
 * extends toward the edges with abstract, unlabeled system domains. The
 * message: "there is much more behind this" — never a roadmap, never
 * "coming soon" product claims.
 */
export function FutureScaleVisual() {
  const { t } = useI18n();
  const c = t.company.future;

  // Edge domains are abstract & unlabeled — just faint system nodes.
  const edgeNodes = [
    { x: 8, y: 14, delay: 0.2 },
    { x: 88, y: 22, delay: 0.4 },
    { x: 16, y: 78, delay: 0.6 },
    { x: 82, y: 82, delay: 0.8 },
    { x: 50, y: 6, delay: 0.3 },
    { x: 6, y: 50, delay: 0.5 },
    { x: 94, y: 55, delay: 0.7 },
  ];

  return (
    <NazmakSection id="future" className="relative overflow-hidden">
      <NazmakHeader badge={c.badge} title={c.title} lead={c.body} align="center" />

      <div className="relative mt-16 overflow-hidden rounded-2xl border border-border bg-card">
        <div className="relative mx-auto aspect-[21/9] w-full max-w-4xl">
          {/* Visible system node: NAZMOS */}
          <motion.div
            className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2"
            initial={{ opacity: 0, scale: 0.8 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 0.7, ease: EASE_STANDARD }}
          >
            <motion.div
              animate={{ boxShadow: ["0 0 30px color-mix(in oklch, var(--brand-teal) 30%, transparent)", "0 0 50px color-mix(in oklch, var(--brand-teal) 40%, transparent)", "0 0 30px color-mix(in oklch, var(--brand-teal) 30%, transparent)"] }}
              transition={{ duration: 5, repeat: Infinity }}
              className="flex h-32 w-32 flex-col items-center justify-center rounded-full border border-primary/40 bg-background"
            >
              <span className="font-mono text-xs font-bold uppercase tracking-[0.2em] text-primary">
                {t.company.hero.denominator}
              </span>
            </motion.div>
          </motion.div>

          {/* Extending network — abstract unlabeled system domains */}
          {edgeNodes.map((n) => (
            <motion.span
              key={`${n.x}-${n.y}`}
              aria-hidden="true"
              className="absolute rounded-full border border-primary/15"
              style={{ left: `${n.x}%`, top: `${n.y}%`, width: 10, height: 10 }}
              initial={{ opacity: 0 }}
              whileInView={{ opacity: [0, 0.6, 0.2] }}
              viewport={{ once: true }}
              transition={{ duration: 1.2, delay: n.delay, repeat: Infinity, repeatDelay: 3 }}
            />
          ))}

          {/* Faint connecting threads out of frame */}
          <svg className="absolute inset-0 h-full w-full" aria-hidden="true" preserveAspectRatio="none" viewBox="0 0 100 40">
            <motion.line
              x1="50" y1="20" x2="8" y2="14" stroke="var(--brand-teal)" strokeOpacity="0.12" strokeWidth="0.3"
              initial={{ pathLength: 0 }} whileInView={{ pathLength: 1 }} viewport={{ once: true }} transition={{ duration: 1, delay: 0.3 }}
            />
            <motion.line
              x1="50" y1="20" x2="88" y2="22" stroke="var(--brand-teal)" strokeOpacity="0.12" strokeWidth="0.3"
              initial={{ pathLength: 0 }} whileInView={{ pathLength: 1 }} viewport={{ once: true }} transition={{ duration: 1, delay: 0.5 }}
            />
            <motion.line
              x1="50" y1="20" x2="16" y2="78" stroke="var(--brand-teal)" strokeOpacity="0.12" strokeWidth="0.3"
              initial={{ pathLength: 0 }} whileInView={{ pathLength: 1 }} viewport={{ once: true }} transition={{ duration: 1, delay: 0.7 }}
            />
          </svg>
        </div>

        <motion.p
          className="pb-8 text-center font-mono text-xs uppercase tracking-[0.25em] text-muted-foreground"
          initial={{ opacity: 0 }} whileInView={{ opacity: 1 }} viewport={{ once: true }} transition={{ duration: 0.6, delay: 0.4 }}
        >
          {c.hint}
        </motion.p>
      </div>
    </NazmakSection>
  );
}

"use client";

import { motion } from "framer-motion";
import { FileSearch, Check } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { useAudit } from "@/components/landing/audit-context";
import { GuestAuditUploader } from "@/components/landing/GuestAuditUploader";

const EASE = [0.22, 1, 0.36, 1] as const;

/**
 * AuditLayer — the in-universe Money Audit state.
 *
 * The audit is not a mock: it embeds the same live GuestAuditUploader used by
 * the audit sections, which posts the user's files to the real /guest-audit
 * endpoint and publishes results into AuditProvider. The layer's job is
 * placement and narrative — Detect → Estimate → Recommend → Simulate → Approve
 * → Execute → Measure — around that genuine flow.
 */
export function AuditLayer({ stacked, onBack }: { stacked: boolean; onBack: () => void }) {
  const { t } = useI18n();
  const { result } = useAudit();

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 12 }}
      transition={{ duration: 0.45, ease: EASE }}
      className={cn(
        stacked
          ? "relative z-40 mt-5"
          : "absolute inset-0 z-40 flex items-start justify-center overflow-y-auto p-4 md:items-center md:p-6",
      )}
    >
      <div
        className={cn(
          "u-panel w-full max-w-2xl rounded-2xl p-5 shadow-elevation-3 backdrop-blur-xl md:p-7",
        )}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="u-gold font-mono text-[11px] uppercase tracking-[0.24em]">
              {t.universe.audit.label}
            </p>
            <h2 className="u-ink mt-2 font-serif text-2xl leading-tight md:text-3xl">
              {t.universe.audit.title}
            </h2>
            <p className="u-ink-dim mt-3 text-sm leading-relaxed">{t.universe.audit.body}</p>
          </div>
          <button
            type="button"
            onClick={onBack}
            className="focus-ring inline-flex shrink-0 items-center gap-1.5 rounded-md border border-border px-3 py-1.5 font-mono text-[11px] uppercase tracking-[0.14em] text-foreground/70 transition-colors hover:bg-card focus:outline-none"
            aria-label={t.universe.backToUniverse}
          >
            {t.universe.backToUniverse}
          </button>
        </div>

        {result && (
          <div className="u-teal-bg-soft u-teal-border mt-4 flex items-start gap-2 rounded-lg border p-3">
            <Check className="u-teal mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <p className="u-ink-dim text-xs leading-relaxed">
              {t.universe.audit.liveNote} {t.universe.audit.sampleNote}
            </p>
          </div>
        )}

        <div className="mt-5">
          <GuestAuditUploader />
        </div>

        <div className="mt-7 grid gap-6 md:grid-cols-2">
          <div>
            <p className="u-ink-faint flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.2em]">
              <FileSearch className="h-3.5 w-3.5" aria-hidden="true" />
              {t.universe.audit.lifecycleTitle}
            </p>
            <ol className="mt-2.5 space-y-1">
              {t.universe.audit.lifecycle.map((step: string, i: number) => (
                <li
                  key={step}
                  className="u-ink-dim flex items-center gap-2 text-[13px]"
                >
                  {/* Gold numerals: every stage of the money lifecycle is value
                      in motion — a first-class accent in both worlds (§36). */}
                  <span className="u-gold u-gold-border grid h-5 w-5 shrink-0 place-items-center rounded-full border font-mono text-[10px]">
                    {i + 1}
                  </span>
                  {step}
                </li>
              ))}
            </ol>
          </div>
          <div>
            <p className="u-ink-faint font-mono text-[10px] uppercase tracking-[0.2em]">
              {t.universe.audit.conceptsTitle}
            </p>
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {t.universe.audit.concepts.map((c: string) => (
                <span
                  key={c}
                  className="u-ink-dim u-teal-border rounded-full border px-2.5 py-1 text-[11px]"
                >
                  {c}
                </span>
              ))}
            </div>
          </div>
        </div>

        <p className="u-ink-faint mt-6 border-t border-border pt-4 font-mono text-[11px] leading-relaxed">
          {t.universe.audit.ctaNote}
        </p>
      </div>
    </motion.div>
  );
}
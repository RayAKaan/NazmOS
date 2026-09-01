"use client";

import type { ReactNode } from "react";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

/**
 * ApprovalPhone — Pass 3 phone chrome (§4d). A real product behavior made visible:
 * recovery actions arrive as owner approvals on WhatsApp. The chassis/screen are
 * hardcoded dark by design (a phone is a phone in either theme); thread copy comes
 * from translations so EN and AR both read natively. Decorative only — no live
 * actions; approval happens in the real product after sign-up.
 */
export function ApprovalPhone({ className }: { className?: string }) {
  const { t, dir } = useI18n();

  return (
    <div className={cn("relative mx-auto w-full max-w-[300px] select-none", className)}>
      <div aria-hidden="true" className="pointer-events-none absolute -inset-5 rounded-[3.5rem] bg-whatsapp/15 blur-3xl" />

      <div className="relative rounded-[2.75rem] border border-brand-night bg-gradient-to-b from-chat-steel via-chat-deep to-brand-night p-[10px] shadow-elevation-3">
        {/* Notch / speaker */}
        <div aria-hidden="true" className="mx-auto mb-2 h-5 w-20 rounded-full bg-brand-night" />

        <div className="overflow-hidden rounded-[2.1rem] bg-chat-deep">
          {/* Status bar */}
          <div aria-hidden="true" className="flex items-center justify-between px-5 pt-3 text-[10px] font-medium text-brand-cream/50">
            <span className="tabular-nums">{t.landing.whatsapp.time}</span>
            <span className="inline-flex gap-1">
              <span className="block h-1 w-2.5 rounded-full bg-current" />
              <span className="block h-1 w-2.5 rounded-full bg-current" />
              <span className="block h-1 w-2.5 rounded-full bg-current" />
            </span>
          </div>

          {/* Chat header */}
          <div className="mt-1 flex items-center gap-2.5 border-b border-brand-cream/10 px-3.5 py-2.5">
            <span className="relative flex h-8 w-8 shrink-0 items-center justify-center overflow-hidden rounded-full bg-gradient-to-br from-whatsapp-mid to-whatsapp-deep text-xs font-bold text-brand-cream">
              {t.landing.whatsapp.contact.slice(0, 1)}
              <span aria-hidden="true" className="absolute inset-0 flex items-end justify-center pb-[3px] text-[6px]">
                <span className="h-3 w-3 rounded-full bg-brand-cream/30" />
              </span>
            </span>
            <div className="min-w-0">
              <p className="truncate text-xs font-semibold text-brand-cream/90">{t.landing.whatsapp.contact}</p>
              <p className="truncate text-[9px] uppercase tracking-[0.14em] text-whatsapp-light/80">
                {t.landing.whatsapp.profile}
              </p>
            </div>
          </div>

          {/* Thread */}
          <div className="space-y-2 px-3 py-4">
            <IncomingBubble time={t.landing.whatsapp.time} rtl={dir === "rtl"}>
              <p className="font-semibold text-brand-night/85">{t.landing.whatsapp.message}</p>
              <p className="mt-1 text-brand-night/80">{t.landing.whatsapp.summary}</p>
            </IncomingBubble>

            <IncomingBubble time={t.landing.whatsapp.time} rtl={dir === "rtl"}>
              <p className="text-brand-night/85">{t.landing.whatsapp.question}</p>
              <div className="mt-2 flex gap-1.5">
                <span className="rounded-full bg-whatsapp-mid px-2.5 py-1 text-[10px] font-bold text-brand-cream">
                  {t.landing.whatsapp.approve}
                </span>
                <span className="rounded-full bg-brand-night/10 px-2.5 py-1 text-[10px] font-semibold text-brand-night/60">
                  {t.landing.whatsapp.later}
                </span>
              </div>
            </IncomingBubble>

            <div className={cn("flex", dir === "rtl" ? "justify-start" : "justify-end")}>
              <div className={cn("max-w-[85%] rounded-2xl rounded-br-sm bg-whatsapp-light px-3 py-2 text-[11px] leading-5 text-brand-night/90")}>
                {t.landing.whatsapp.confirmed}
                <span className="ml-2 inline-block align-bottom text-[9px] text-brand-night/50">{t.landing.whatsapp.time}</span>
              </div>
            </div>

            <div className={cn("pt-1 text-center text-[9px] uppercase tracking-[0.14em] text-brand-cream/40")}>
              {t.landing.whatsapp.note}
            </div>
          </div>

          {/* Input bar */}
          <div className="flex items-center gap-2 border-t border-brand-cream/10 px-3 py-2.5">
            <div className="flex-1 rounded-full bg-brand-cream/10 px-3 py-1.5 text-[10px] text-brand-cream/45">
              {t.landing.whatsapp.contact}
            </div>
            <div aria-hidden="true" className="h-6 w-6 rounded-full bg-whatsapp-mid" />
          </div>
        </div>
      </div>
    </div>
  );
}

function IncomingBubble({
  children,
  time,
  rtl,
}: {
  children: ReactNode;
  time: string;
  rtl: boolean;
}) {
  return (
    <div className={cn("flex", rtl ? "justify-end" : "justify-start")}>
      <div className={cn("max-w-[85%] rounded-2xl rounded-bl-sm bg-whatsapp-faint px-3 py-2 text-[11px] leading-5 [overflow-wrap:anywhere]")}>
        {children}
        <span className="mt-0.5 block text-right text-[9px] text-brand-night/45">{time}</span>
      </div>
    </div>
  );
}
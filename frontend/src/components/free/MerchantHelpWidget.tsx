"use client";

import { useState } from "react";
import { CheckCircle2, Clipboard, MessageCircle, X } from "lucide-react";

const HELP_MESSAGE = `Assalamu alaikum Nazmak, I need help with my Free Money Audit.\n\nMy store type:\nMy POS / Excel system:\nI have: sales file / inventory file / both\nThe confusing column is:\n`; 

export function MerchantHelpWidget() {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const copyMessage = async () => {
    try {
      await navigator.clipboard.writeText(HELP_MESSAGE);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="fixed bottom-24 right-4 z-50 md:bottom-6">
      {open && (
        <div className="mb-3 w-[min(92vw,360px)] rounded-3xl border border-white/10 bg-brand-night p-4 text-white shadow-2xl shadow-black/40">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-brand-amber">Founder help</p>
              <h3 className="mt-2 text-lg font-black">Stuck on files?</h3>
              <p className="mt-2 text-sm leading-6 text-white/60">
                The best products reduce user confusion fast. Copy this support message, paste it to the founder/support channel,
                and include one screenshot of your columns.
              </p>
            </div>
            <button onClick={() => setOpen(false)} className="rounded-full p-1 text-white/50 hover:bg-white/10 hover:text-white" aria-label="Close help">
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="mt-4 rounded-2xl bg-white/[0.04] p-3 text-xs leading-5 text-white/55 ring-1 ring-white/5">
            <p>Common issues:</p>
            <ul className="mt-2 list-disc space-y-1 pl-4">
              <li>You do not know whether a file is sales or inventory.</li>
              <li>Your POS columns are in Arabic or abbreviated.</li>
              <li>Cost price is missing, so trapped-cash value looks low.</li>
            </ul>
          </div>

          <button
            onClick={copyMessage}
            className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl bg-brand-amber px-4 py-3 text-sm font-bold text-black hover:bg-brand-gold"
          >
            {copied ? <CheckCircle2 className="h-4 w-4" /> : <Clipboard className="h-4 w-4" />}
            {copied ? "Message copied" : "Copy help message"}
          </button>
        </div>
      )}

      <button
        onClick={() => setOpen((value) => !value)}
        className="flex items-center gap-2 rounded-full border border-brand-amber/40 bg-brand-night px-4 py-3 text-sm font-bold text-brand-amber shadow-2xl shadow-black/30 hover:bg-brand-amber hover:text-black"
      >
        <MessageCircle className="h-4 w-4" /> Need help?
      </button>
    </div>
  );
}

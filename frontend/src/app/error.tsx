"use client";

import { AlertTriangle } from "lucide-react";
import { errorMessage } from "@/lib/utils";

export default function RootError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-brand-night p-6 text-white">
      <section className="w-full max-w-md rounded-3xl border border-white/10 bg-white/[0.03] p-8 text-center">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-red/10">
          <AlertTriangle className="h-7 w-7 text-brand-red-light" aria-hidden />
        </div>
        <h1 className="mt-5 text-xl font-bold">Something went wrong</h1>
        <p className="mt-2 text-sm leading-6 text-white/62">
          {errorMessage(error, "This page hit an unexpected error. Try again, and if it keeps happening, reach out.")}
        </p>
        <button
          onClick={reset}
          className="mt-6 inline-flex items-center justify-center rounded-xl bg-brand-amber px-5 py-3 font-bold text-black hover:bg-brand-gold"
        >
          Try again
        </button>
      </section>
    </div>
  );
}

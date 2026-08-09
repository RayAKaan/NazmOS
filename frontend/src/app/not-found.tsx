import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-brand-night px-5 py-20 text-brand-cream">
      <div className="max-w-lg text-center">
        <p className="font-mono text-xs font-bold uppercase tracking-[0.28em] text-brand-amber">404</p>
        <h1 className="mt-4 font-serif text-5xl font-black leading-[0.95] tracking-[-0.04em] md:text-7xl">
          Page not found
        </h1>
        <p className="mt-6 text-lg leading-8 text-brand-cream/62">
          The page you are looking for does not exist or has been moved.
        </p>
        <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
          <Link
            href="/"
            className="inline-flex items-center justify-center rounded-2xl bg-brand-amber px-6 py-3 font-bold text-brand-night hover:bg-brand-gold-soft"
          >
            Back to NazmOS
          </Link>
          <Link
            href="/product-demo"
            className="inline-flex items-center justify-center rounded-2xl border border-brand-cream/10 px-6 py-3 font-semibold text-brand-cream/80 hover:bg-brand-cream/5"
          >
            Run interactive demo
          </Link>
        </div>
      </div>
    </main>
  );
}

import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[#0A0E0C] px-5 py-20 text-[#F4EFE6]">
      <div className="max-w-lg text-center">
        <p className="font-mono text-xs font-bold uppercase tracking-[0.28em] text-[#E0B34A]">404</p>
        <h1 className="mt-4 font-serif text-5xl font-black leading-[0.95] tracking-[-0.04em] md:text-7xl">
          Page not found
        </h1>
        <p className="mt-6 text-lg leading-8 text-white/62">
          The page you are looking for does not exist or has been moved.
        </p>
        <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
          <Link
            href="/"
            className="inline-flex items-center justify-center rounded-2xl bg-[#E0B34A] px-6 py-3 font-bold text-[#0A0E0C] hover:bg-[#f0c765]"
          >
            Back to NazmOS
          </Link>
          <Link
            href="/product-demo"
            className="inline-flex items-center justify-center rounded-2xl border border-white/10 px-6 py-3 font-semibold text-white/80 hover:bg-white/5"
          >
            Run interactive demo
          </Link>
        </div>
      </div>
    </main>
  );
}

import { WeaveTile } from "@/components/ui/WeaveTile";

/**
 * HeroPlate — the hero's full-bleed "signature moment" background (Pass 3).
 *
 * Renders a brand-night cinematic plate from CSS/SVG only (no AI/diffusion, per
 * build doctrine). To swap in a real still, drop a file at
 * `frontend/public/marketing/hero-riyadh-aerial.jpg` — the photo layer activates
 * automatically (missing file renders nothing, so procedural art stays until then).
 * Zero code change required.
 */
export function HeroPlate() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden bg-brand-night">
      {/* Photo slot — silent while the file is absent. */}
      <div
        className="absolute inset-0 opacity-70"
        style={{
          backgroundImage: "url('/marketing/hero-riyadh-aerial.jpg')",
          backgroundSize: "cover",
          backgroundPosition: "center",
        }}
      />

      {/* Procedural aurora — visible until (and behind) the photo layer. */}
      <div
        className="absolute -left-1/4 -top-1/3 h-[85%] w-[75%] rounded-full opacity-50 blur-[130px]"
        style={{
          background:
            "radial-gradient(circle at 45% 40%, var(--brand-teal-dark), transparent 70%)",
        }}
      />
      <div
        className="absolute -bottom-1/4 -right-1/4 h-[55%] w-[50%] rounded-full opacity-20 blur-[120px]"
        style={{
          background:
            "radial-gradient(circle at 60% 60%, var(--brand-gold), transparent 72%)",
        }}
      />

      <WeaveTile variant="field" color="teal" opacity={0.05} />

      {/* Abstract recovery arcs — two stores exchanging surplus, not a map. */}
      <svg
        className="absolute -bottom-[6%] -right-[8%] h-[65%] w-[65%]"
        viewBox="0 0 400 260"
        fill="none"
        aria-hidden="true"
      >
        <defs>
          <linearGradient id="hero-arc-gold" x1="0" y1="1" x2="1" y2="0">
            <stop offset="0%" stopColor="var(--brand-gold)" stopOpacity="0" />
            <stop offset="50%" stopColor="var(--brand-gold)" stopOpacity="0.4" />
            <stop offset="100%" stopColor="var(--brand-teal)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path
          d="M30 230 C 140 60, 260 60, 372 150"
          stroke="url(#hero-arc-gold)"
          strokeWidth="2"
          strokeLinecap="round"
        />
        <path
          d="M48 240 C 150 110, 260 110, 360 176"
          stroke="var(--brand-teal)"
          strokeOpacity="0.5"
          strokeWidth="1.5"
          strokeDasharray="2 8"
          strokeLinecap="round"
        />
        <circle cx="30" cy="230" r="3.5" fill="var(--brand-gold)" opacity="0.9" />
        <circle cx="372" cy="150" r="3.5" fill="var(--brand-teal)" opacity="0.9" />
        <circle cx="48" cy="240" r="2.5" fill="var(--brand-teal)" opacity="0.7" />
        <circle cx="360" cy="176" r="2.5" fill="var(--brand-gold)" opacity="0.7" />
      </svg>

      {/* Subtle regatta grid */}
      <div className="absolute inset-0 opacity-[0.025] [background-image:linear-gradient(var(--foreground)_1px,transparent_1px),linear-gradient(90deg,var(--foreground)_1px,transparent_1px)] [background-size:72px_72px]" />

      {/* Legibility scrims over every layer. */}
      <div className="absolute inset-0 bg-gradient-to-t from-brand-night via-brand-night/70 to-brand-night/30" />
      <div className="absolute inset-0 bg-gradient-to-r from-brand-night/95 via-brand-night/40 to-transparent" />
    </div>
  );
}
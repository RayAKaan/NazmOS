import { WeaveTile } from "@/components/ui/WeaveTile";

/**
 * FeaturedPlate — the Problem section's `01 Cash leakage` editorial plate.
 * Brand-red moment, photo-ready: drop `public/marketing/pharmacy-shelf.jpg` to
 * activate the still; the procedural art otherwise carries the moment.
 */
export function FeaturedPlate() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden bg-brand-night">
      {/* Photo slot — silent while absent. */}
      <div
        className="absolute inset-0 opacity-60"
        style={{
          backgroundImage: "url('/marketing/pharmacy-shelf.jpg')",
          backgroundSize: "cover",
          backgroundPosition: "center",
        }}
      />

      {/* Red aurora — the one-time risk moment. */}
      <div
        className="absolute -right-1/4 -top-1/3 h-[90%] w-[70%] rounded-full opacity-50 blur-[120px]"
        style={{
          background:
            "radial-gradient(circle at 65% 30%, var(--brand-red), transparent 68%)",
        }}
      />

      <WeaveTile variant="field" color="teal" opacity={0.03} />

      {/* Soft flecks standing in for shelf light. */}
      <div className="absolute inset-0 opacity-[0.05] [background-image:radial-gradient(var(--brand-red-light)_1px,transparent_1px)] [background-size:22px_22px]" />

      {/* Bottom-legibility scrim for the stacked editorial text. */}
      <div className="absolute inset-0 bg-gradient-to-t from-brand-night via-brand-night/65 to-brand-night/15" />
    </div>
  );
}
// Shared landing logo mark — a self-contained SVG so it can be used in the header,
// footer, and hero without duplicating markup. Colored via CSS `color`/`currentColor`.
export const logoMark = {
  Svg: function LogoSvg({ className }: { className?: string }) {
    return (
      <svg viewBox="0 0 96 96" className={className} aria-hidden="true">
        <defs>
          <linearGradient id="nazm-mark-gold" x1="0" x2="1" y1="0" y2="1">
            <stop offset="0%" stopColor="var(--brand-gold)" />
            <stop offset="55%" stopColor="var(--brand-gold-soft)" />
            <stop offset="100%" stopColor="var(--brand-sand)" />
          </linearGradient>
        </defs>
        <path
          d="M19 62 C33 62 39 50 48 41 C56 32 64 29 77 35"
          fill="none"
          stroke="url(#nazm-mark-gold)"
          strokeWidth="14"
          strokeLinecap="round"
        />
        <path
          d="M33 64 C44 64 52 60 58 51"
          fill="none"
          stroke="url(#nazm-mark-gold)"
          strokeWidth="10"
          strokeLinecap="round"
          opacity="0.92"
        />
        <rect x="44" y="13" width="14" height="14" rx="2" fill="url(#nazm-mark-gold)" transform="rotate(45 51 20)" />
      </svg>
    );
  },
};

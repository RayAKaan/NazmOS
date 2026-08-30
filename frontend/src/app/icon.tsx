import { ImageResponse } from "next/og";

export const size = { width: 512, height: 512 };
export const contentType = "image/png";

// NOTE (§10 flag): next/og's Satori renderer has no access to CSS variables or Tailwind,
// so these MUST be literal hex. They mirror tokens.json seeds by hand:
//   BRAND_NIGHT #0A0E0C  (--brand-night)  ·  BRAND_GOLD #F2CF69 (--brand-gold)
// Keep in sync with design-tokens/tokens.json.
const BRAND_NIGHT = "#0A0E0C";
const BRAND_GOLD = "#F2CF69";

export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: BRAND_NIGHT,
        }}
      >
        <div
          style={{
            fontSize: 280,
            fontWeight: 800,
            fontFamily: "ui-sans-serif, system-ui, sans-serif",
            color: BRAND_GOLD,
            lineHeight: 1,
          }}
        >
          N
        </div>
      </div>
    ),
    size
  );
}

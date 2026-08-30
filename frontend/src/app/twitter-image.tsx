import { ImageResponse } from "next/og";

export const size = { width: 1200, height: 600 };
export const contentType = "image/png";

// NOTE (§10 flag): Satori has no CSS-variable/Tailwind support, so these are literal hex
// synced by hand to tokens.json seeds (see opengraph-image.tsx).
const BRAND_NIGHT = "#0A0E0C";
const BRAND_TEAL = "#14B8A6";
const BRAND_GOLD = "#F2CF69";
const BRAND_CREAM = "#F4EFE6";

export default function TwitterImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: 80,
          background: BRAND_NIGHT,
        }}
      >
        <div
          style={{
            fontSize: 26,
            fontWeight: 600,
            fontFamily: "ui-monospace, monospace",
            color: BRAND_GOLD,
            letterSpacing: "0.2em",
            textTransform: "uppercase",
          }}
        >
          Nazmak · NazmOS
        </div>
        <div
          style={{
            marginTop: 24,
            fontSize: 108,
            fontWeight: 900,
            fontFamily: "ui-sans-serif, system-ui, sans-serif",
            color: BRAND_CREAM,
            letterSpacing: "-0.04em",
            lineHeight: 1.05,
          }}
        >
          Inventory Intelligence OS
        </div>
        <div
          style={{
            marginTop: 16,
            fontSize: 40,
            fontWeight: 600,
            fontFamily: "ui-sans-serif, system-ui, sans-serif",
            color: BRAND_TEAL,
            letterSpacing: "-0.02em",
          }}
        >
          nazm.ai
        </div>
      </div>
    ),
    size
  );
}

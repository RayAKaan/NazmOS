import { ImageResponse } from "next/og";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

// NOTE (§10 flag): Satori has no CSS-variable/Tailwind support, so these are literal hex
// synced by hand to tokens.json seeds:
//   BRAND_NIGHT #0A0E0C · BRAND_TEAL #14B8A6 · BRAND_GOLD #F2CF69 · BRAND_CREAM #F4EFE6
const BRAND_NIGHT = "#0A0E0C";
const BRAND_TEAL = "#14B8A6";
const BRAND_GOLD = "#F2CF69";
const BRAND_CREAM = "#F4EFE6";
const BRAND_CREAM_MUTED = "rgba(244, 239, 230, 0.55)";

export default function OpenGraphImage() {
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
            fontSize: 28,
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
            fontSize: 120,
            fontWeight: 900,
            fontFamily: "ui-sans-serif, system-ui, sans-serif",
            color: BRAND_CREAM,
            letterSpacing: "-0.04em",
            lineHeight: 1,
          }}
        >
          Find the cash trapped
        </div>
        <div
          style={{
            marginTop: 8,
            fontSize: 120,
            fontWeight: 900,
            fontFamily: "ui-sans-serif, system-ui, sans-serif",
            color: BRAND_TEAL,
            letterSpacing: "-0.04em",
            lineHeight: 1,
          }}
        >
          inside your store.
        </div>
        <div
          style={{
            position: "absolute",
            bottom: 48,
            right: 64,
            fontSize: 28,
            fontWeight: 500,
            color: BRAND_CREAM_MUTED,
            fontFamily: "ui-monospace, monospace",
          }}
        >
          nazm.ai
        </div>
      </div>
    ),
    size
  );
}

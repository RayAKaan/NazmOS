import { ImageResponse } from "next/og";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const BG_FROM = "#0a0a0f";
const BG_TO = "#1a1a2e";
const FG = "#ffffff";
const ACCENT = "#14B8A6";
const MUTED = "#94a3b8";

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
          background: `linear-gradient(135deg, ${BG_FROM} 0%, ${BG_TO} 100%)`,
        }}
      >
        <div
          style={{
            fontSize: 120,
            fontWeight: 900,
            fontFamily: "ui-sans-serif, system-ui, sans-serif",
            color: FG,
            letterSpacing: "-0.04em",
            lineHeight: 1,
          }}
        >
          NazmOS
        </div>
        <div
          style={{
            marginTop: 24,
            fontSize: 44,
            fontWeight: 600,
            fontFamily: "ui-sans-serif, system-ui, sans-serif",
            color: ACCENT,
            letterSpacing: "-0.02em",
          }}
        >
          Inventory Intelligence OS
        </div>
        <div
          style={{
            position: "absolute",
            bottom: 48,
            right: 64,
            fontSize: 28,
            fontWeight: 500,
            color: MUTED,
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

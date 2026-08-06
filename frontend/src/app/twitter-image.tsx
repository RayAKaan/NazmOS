import { ImageResponse } from "next/og";

export const size = { width: 1200, height: 600 };
export const contentType = "image/png";

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
          background: "linear-gradient(135deg, #0a0a0f 0%, #1a1a2e 100%)",
        }}
      >
        <div
          style={{
            fontSize: 120,
            fontWeight: 900,
            fontFamily: "ui-sans-serif, system-ui, sans-serif",
            color: "#ffffff",
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
            color: "#14B8A6",
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
            color: "#94a3b8",
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

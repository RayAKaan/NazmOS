import { ImageResponse } from "next/og";

export const size = { width: 512, height: 512 };
export const contentType = "image/png";

const BG_FROM = "#0a0a0f";
const ACCENT = "#14B8A6";

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
          background: BG_FROM,
        }}
      >
        <div
          style={{
            fontSize: 280,
            fontWeight: 800,
            fontFamily: "ui-sans-serif, system-ui, sans-serif",
            color: ACCENT,
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

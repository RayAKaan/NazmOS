import { ImageResponse } from "next/og";

export const size = { width: 512, height: 512 };
export const contentType = "image/png";

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
          background: "#0a0a0f",
        }}
      >
        <div
          style={{
            fontSize: 280,
            fontWeight: 800,
            fontFamily: "ui-sans-serif, system-ui, sans-serif",
            color: "#14B8A6",
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

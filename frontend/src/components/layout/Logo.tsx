export function Logo({ size = "default" }: { size?: "small" | "default" }) {
  return (
    <div className="flex items-center gap-2">
      <div
        className={`rounded-lg bg-primary flex items-center justify-center ${
          size === "small" ? "w-8 h-8" : "w-10 h-10"
        }`}
      >
        <span
          className={`text-primary-foreground font-bold ${
            size === "small" ? "text-lg" : "text-xl"
          }`}
        >
          S
        </span>
      </div>
      {size !== "small" && (
        <div>
          <div className="font-bold text-lg leading-none">NazmOS</div>
          <p className="text-xs text-muted-foreground leading-none mt-0.5">AI-Powered</p>
        </div>
      )}
    </div>
  );
}

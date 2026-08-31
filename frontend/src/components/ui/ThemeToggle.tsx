"use client";

import { useEffect, useState } from "react";
import { Moon, Sun, Monitor } from "lucide-react";
import { cn } from "@/lib/utils";

type ThemeMode = "system" | "light" | "dark";

const MODES: { value: ThemeMode; icon: typeof Sun; label: string }[] = [
  { value: "light", icon: Sun, label: "Light" },
  { value: "system", icon: Monitor, label: "System" },
  { value: "dark", icon: Moon, label: "Dark" },
];

const STORAGE_KEY = "nazmos-theme";

function applyTheme(mode: ThemeMode) {
  const prefersDark =
    typeof window !== "undefined" &&
    window.matchMedia &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;
  const dark = mode === "dark" || (mode === "system" && !!prefersDark);
  document.documentElement.classList.toggle("dark", dark);
}

export function ThemeToggle() {
  const [mode, setMode] = useState<ThemeMode>("system");

  useEffect(() => {
    const stored = (localStorage.getItem(STORAGE_KEY) as ThemeMode | null) ?? "system";
    setMode(stored);
    applyTheme(stored);

    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onSystemChange = () => {
      if ((localStorage.getItem(STORAGE_KEY) ?? "system") === "system") applyTheme("system");
    };
    media.addEventListener("change", onSystemChange);
    return () => media.removeEventListener("change", onSystemChange);
  }, []);

  const select = (next: ThemeMode) => {
    setMode(next);
    applyTheme(next);
    // "system" still applies a concrete class; keep stored value meaningful.
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* storage unavailable */
    }
  };

  return (
    <div
      role="group"
      aria-label="Theme"
      className="inline-flex items-center rounded-lg border border-border bg-muted/40 p-0.5"
    >
      {MODES.map(({ value, icon: Icon, label }) => (
        <button
          key={value}
          type="button"
          onClick={() => select(value)}
          aria-pressed={mode === value}
          aria-label={`${label} theme`}
          title={`${label} theme`}
          className={cn(
            "p-2 rounded-md text-muted-foreground transition-colors",
            mode === value ? "bg-background text-foreground shadow-subtle" : "hover:text-foreground"
          )}
        >
          <Icon className="w-4 h-4" />
        </button>
      ))}
    </div>
  );
}

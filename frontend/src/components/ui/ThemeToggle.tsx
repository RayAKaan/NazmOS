"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

// Theme toggle gate (B1). Default is DARK (html.dark set in root layout). The toggle
// persists a stored preference and flips the .dark class; light mode is reachable so
// the light token pair in globals.css is exercised, while dark remains the default.
export function ThemeToggle() {
  const [dark, setDark] = useState(true);

  useEffect(() => {
    let stored: string | null = null;
    try {
      stored = localStorage.getItem("nazmos-theme");
    } catch {
      /* SSR / storage unavailable */
    }
    const initial = stored ? stored === "dark" : true;
    setDark(initial);
    document.documentElement.classList.toggle("dark", initial);
  }, []);

  const toggle = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("nazmos-theme", next ? "dark" : "light");
    } catch {
      /* ignore */
    }
  };

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
      className="p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
    >
      {dark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
    </button>
  );
}

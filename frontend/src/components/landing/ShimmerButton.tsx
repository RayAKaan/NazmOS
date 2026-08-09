"use client";

import { cn } from "@/lib/utils";

interface ShimmerButtonProps {
  children: React.ReactNode;
  className?: string;
  onClick?: () => void;
}

export function ShimmerButton({ children, className, onClick }: ShimmerButtonProps) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "relative inline-flex items-center justify-center px-8 py-4 rounded-xl overflow-hidden transition-all duration-300",
        "bg-gradient-to-r from-brand-primary to-brand-secondary",
        "text-brand-night font-semibold",
        "hover:shadow-glow-gold hover:scale-105",
        "active:scale-95",
        "before:absolute before:inset-0 before:bg-gradient-to-r before:from-transparent before:via-brand-cream/20 before:to-transparent",
        "before:translate-x-[-200%] before:animate-shimmer",
        className
      )}
    >
      {children}
    </button>
  );
}

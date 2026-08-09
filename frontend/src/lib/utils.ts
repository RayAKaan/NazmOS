import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(value: number | string | null | undefined) {
  const num = Number(value ?? 0);
  return new Intl.NumberFormat("en-SA", {
    style: "currency",
    currency: "SAR",
    maximumFractionDigits: 2,
  }).format(Number.isFinite(num) ? num : 0);
}

export function formatPercent(value: number | string | null | undefined) {
  const num = Number(value ?? 0);
  if (!Number.isFinite(num)) return "0.0%";
  return `${num >= 0 ? "+" : ""}${num.toFixed(1)}%`;
}

export function formatDate(value: string | Date | null | undefined) {
  if (!value) return "—";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-SA", {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(date);
}

export function getGreeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

export function errorMessage(err: unknown, fallback: string): string {
  const detail = (err as any)?.response?.data?.detail;
  if (typeof detail === "string" && detail.length > 0) return detail;
  if (Array.isArray(detail)) {
    const first = detail[0]?.msg;
    if (typeof first === "string") return first;
  }
  if (typeof (err as any)?.message === "string") {
    const msg = (err as any).message;
    if (msg !== "Network Error") return msg;
  }
  return fallback;
}

// lib/utils.ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { RiskLevel, Recommendation } from "./api";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(amount: number | null, currency = "USD"): string {
  if (amount == null) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(amount);
}

export function formatMinutes(minutes: number | null): string {
  if (minutes == null) return "—";
  if (minutes < 60) return `${Math.round(minutes)}m`;
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

export function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export function riskColors(level: RiskLevel | null) {
  switch (level) {
    case "HIGH":
      return {
        bg: "bg-red-50",
        border: "border-red-200",
        text: "text-red-700",
        badge: "bg-red-100 text-red-800 ring-red-600/20",
        dot: "bg-red-500",
        bar: "bg-red-500",
      };
    case "MEDIUM":
      return {
        bg: "bg-amber-50",
        border: "border-amber-200",
        text: "text-amber-700",
        badge: "bg-amber-100 text-amber-800 ring-amber-600/20",
        dot: "bg-amber-500",
        bar: "bg-amber-500",
      };
    case "LOW":
    default:
      return {
        bg: "bg-emerald-50",
        border: "border-emerald-200",
        text: "text-emerald-700",
        badge: "bg-emerald-100 text-emerald-800 ring-emerald-600/20",
        dot: "bg-emerald-500",
        bar: "bg-emerald-500",
      };
  }
}

export function recColors(rec: Recommendation | null) {
  switch (rec) {
    case "APPROVE":
      return "bg-emerald-100 text-emerald-800";
    case "REJECT":
      return "bg-red-100 text-red-800";
    case "ESCALATE":
    default:
      return "bg-amber-100 text-amber-800";
  }
}

export function countryName(code: string | null): string {
  if (!code) return "—";
  try {
    return (
      new Intl.DisplayNames(["en"], { type: "region" }).of(code) ?? code
    );
  } catch {
    return code;
  }
}

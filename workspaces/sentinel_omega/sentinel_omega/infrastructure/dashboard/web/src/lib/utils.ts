import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function fmtNum(n: unknown, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return "—";
  return Number(n).toFixed(digits);
}

export function fmtTs(ts: unknown): string {
  if (ts === null || ts === undefined || ts === "") return "—";
  const n = Number(ts);
  if (Number.isFinite(n) && n > 1e11) {
    return new Date(n).toLocaleString("es-MX", { timeZone: "America/Mexico_City" });
  }
  if (Number.isFinite(n) && n > 1e9) {
    return new Date(n * 1000).toLocaleString("es-MX", { timeZone: "America/Mexico_City" });
  }
  const s = String(ts);
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) return s;
  return "—";
}

export function riskColor(level?: string | null): string {
  switch ((level || "").toUpperCase()) {
    case "LOW":
      return "#10b981";
    case "MODERATE":
      return "#ffc107";
    case "HIGH":
      return "#ff9100";
    case "CRITICAL":
      return "#ff1744";
    default:
      return "#8a8f98";
  }
}

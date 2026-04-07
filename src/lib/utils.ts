import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Format price with proper decimal places for gold
 * XAU/USD typically uses 2 decimal places
 */
export function formatPrice(price: number | null | undefined): string {
  if (price === null || price === undefined) return "0.00";
  return price.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/**
 * Format percentage with 1 decimal place
 */
export function formatPercent(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

/**
 * Format confidence score as percentage
 */
export function formatConfidence(value: number): string {
  return `${Math.round(value)}%`;
}

/**
 * Calculate pips difference for XAU/USD
 * 1 pip = $0.10 for gold
 */
export function calculatePips(entry: number, target: number): number {
  return Math.round(Math.abs(target - entry) * 10);
}

/**
 * Get risk-reward ratio
 */
export function getRiskReward(
  entry: number,
  sl: number,
  tp: number
): string {
  const risk = Math.abs(entry - sl);
  const reward = Math.abs(tp - entry);
  if (risk === 0) return "0:0";
  const ratio = reward / risk;
  return `1:${ratio.toFixed(1)}`;
}

/**
 * Format relative time (e.g., "2m ago", "1h ago")
 */
export function formatRelativeTime(date: Date): string {
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  const diffHr = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHr / 24);

  if (diffMin < 1) return "Just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHr < 24) return `${diffHr}h ago`;
  return `${diffDay}d ago`;
}

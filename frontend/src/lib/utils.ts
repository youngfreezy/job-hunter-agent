import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function riskColor(score: number) {
  if (score >= 70) return "text-red-500";
  if (score >= 40) return "text-yellow-500";
  return "text-green-500";
}

export function riskLabel(score: number) {
  if (score >= 70) return "HIGH RISK";
  if (score >= 40) return "MODERATE RISK";
  return "LOW RISK";
}

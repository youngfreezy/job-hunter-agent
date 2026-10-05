// Copyright (c) 2026 V2 Software LLC. All rights reserved.

function _resolveApiBase(): string {
  if (process.env.NEXT_PUBLIC_API_URL) return process.env.NEXT_PUBLIC_API_URL;
  if (process.env.NODE_ENV === "production") {
    throw new Error("NEXT_PUBLIC_API_URL must be set in production");
  }
  return typeof window !== "undefined" && ["3000", "3001"].includes(window.location.port)
    ? "http://localhost:8000"
    : "";
}

export const API_BASE = _resolveApiBase();

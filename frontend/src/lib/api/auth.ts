// Copyright (c) 2026 V2 Software LLC. All rights reserved.

function getCsrfToken(): string {
  if (typeof document === "undefined") return "";
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : "";
}

function csrfHeaders(): Record<string, string> {
  const token = getCsrfToken();
  return token ? { "x-csrf-token": token } : {};
}

let _cachedToken: string | null = null;

let _tokenFetchedAt = 0;

const _TOKEN_TTL_MS = 5 * 60 * 1000;

export async function getAuthHeaders(): Promise<Record<string, string>> {
  // Return cached JWT if still fresh
  if (_cachedToken && Date.now() - _tokenFetchedAt < _TOKEN_TTL_MS) {
    return { Authorization: `Bearer ${_cachedToken}`, ...csrfHeaders() };
  }
  try {
    const res = await fetch("/api/auth/token");
    if (res.ok) {
      const { token } = await res.json();
      if (token) {
        _cachedToken = token;
        _tokenFetchedAt = Date.now();
        return { Authorization: `Bearer ${token}`, ...csrfHeaders() };
      }
    }
  } catch {}
  return csrfHeaders();
}

// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { toast } from "sonner";
import { getAuthHeaders } from "./auth";

let _lastRateLimitToast = 0;

export async function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const res = await fetch(input, init);
  if (res.status === 429) {
    const now = Date.now();
    // Debounce: only show one toast per 5 seconds
    if (now - _lastRateLimitToast > 5000) {
      _lastRateLimitToast = now;
      const retryAfter = res.headers.get("Retry-After");
      const msg = retryAfter
        ? `Too many requests — please wait ${retryAfter}s and try again.`
        : "Too many requests — please wait a moment and try again.";
      toast.error(msg);
    }
  }
  return res;
}

/** One authenticated request; mutations are never retried by the transport. */
export async function authenticatedFetch(
  input: RequestInfo | URL,
  init: Omit<RequestInit, "headers"> & { headers?: Record<string, string> } = {}
): Promise<Response> {
  const auth = await getAuthHeaders();
  return apiFetch(input, { ...init, headers: { ...init.headers, ...auth } });
}

export async function throwApiError(res: Response): Promise<never> {
  let detail = res.statusText;
  try {
    const body = await res.json();
    if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
  } catch {}
  throw new Error(detail || `Request failed (${res.status})`);
}

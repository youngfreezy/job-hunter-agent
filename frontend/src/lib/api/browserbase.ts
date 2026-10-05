// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { API_BASE } from "./config";
import { authenticatedFetch } from "./transport";

export interface BrowserbaseSettings {
  api_key_set: boolean;
  api_key_hint: string | null;
  project_id: string;
  proxies: boolean;
  context_ids: Record<string, string>;
  boards: string[];
  login_capture_boards: string[];
  env_configured: boolean;
  effective_configured: boolean;
  effective_context_ids?: Record<string, string>;
}

export interface BrowserbaseSettingsUpdate {
  /** Omit to keep the stored key; empty string clears it. */
  api_key?: string;
  project_id: string;
  proxies: boolean;
  context_ids: Record<string, string>;
}

export interface BrowserbaseLoginSession {
  capture_id: string;
  board: string;
  status: "waiting" | "captured" | "timeout" | "error" | "cancelled";
  context_id: string | null;
  browserbase_session_id: string;
  live_view_url: string | null;
  error: string | null;
  elapsed_seconds: number;
}

export async function getBrowserbaseSettings(): Promise<BrowserbaseSettings> {
  const res = await authenticatedFetch(`${API_BASE}/api/browserbase/settings`, {});
  if (!res.ok) throw new Error("Failed to load Browserbase settings");
  return res.json();
}

export async function saveBrowserbaseSettings(
  update: BrowserbaseSettingsUpdate
): Promise<BrowserbaseSettings> {
  const res = await authenticatedFetch(`${API_BASE}/api/browserbase/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(update),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || "Failed to save Browserbase settings");
  }
  return res.json();
}

export async function startBrowserbaseLogin(board: string): Promise<BrowserbaseLoginSession> {
  const res = await authenticatedFetch(`${API_BASE}/api/browserbase/login-sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ board }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || "Failed to start Browserbase login session");
  }
  return res.json();
}

export async function getBrowserbaseLogin(captureId: string): Promise<BrowserbaseLoginSession> {
  const res = await authenticatedFetch(`${API_BASE}/api/browserbase/login-sessions/${captureId}`, {
  });
  if (!res.ok) throw new Error("Failed to read Browserbase login session");
  return res.json();
}

export async function cancelBrowserbaseLogin(captureId: string): Promise<void> {
  await authenticatedFetch(`${API_BASE}/api/browserbase/login-sessions/${captureId}`, {
    method: "DELETE",
  });
}

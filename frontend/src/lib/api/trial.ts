// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { API_BASE } from "./config";
import { apiFetch, throwApiError } from "./transport";
import { AuthenticatedEventSource } from "../event-stream";
import { subscribeToSessionEvents, type SSEConnection } from "./streams";

const TRIAL_TOKEN_KEY = "jh_trial_token";

const TRIAL_EMAIL_KEY = "jh_trial_email";

export function getTrialToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TRIAL_TOKEN_KEY);
}

export function setTrialData(token: string, email: string): void {
  localStorage.setItem(TRIAL_TOKEN_KEY, token);
  localStorage.setItem(TRIAL_EMAIL_KEY, email);
}

export function getTrialEmail(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TRIAL_EMAIL_KEY);
}

export function clearTrialData(): void {
  localStorage.removeItem(TRIAL_TOKEN_KEY);
  localStorage.removeItem(TRIAL_EMAIL_KEY);
}

export async function parseResumeTrial(
  file: File
): Promise<{ text: string; filename: string; file_path?: string; resume_uuid?: string }> {
  const form = new FormData();
  form.append("file", file);
  const res = await apiFetch(`${API_BASE}/api/free-trial/parse-resume`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail || `Failed to parse resume: ${res.statusText}`);
  }
  return res.json();
}

export async function startFreeTrialSession(params: {
  keywords: string[];
  locations: string[];
  remote_only: boolean;
  salary_min: number | null;
  search_radius?: number;
  resume_text: string | null;
  resume_file_path: string | null;
  resume_uuid: string | null;
  linkedin_url: string | null;
  preferences: Record<string, unknown>;
  config?: {
    max_jobs: number;
    tailoring_quality: string;
    application_mode: string;
    generate_cover_letters: boolean;
    job_boards: string[];
  };
}): Promise<{ session_id: string; trial_token: string; email: string; name: string | null }> {
  const res = await apiFetch(`${API_BASE}/api/free-trial/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) await throwApiError(res);
  const data = await res.json();
  setTrialData(data.trial_token, data.email);
  return data;
}

export function createTrialSSEConnection(sessionId: string): SSEConnection {
  return new AuthenticatedEventSource(`${API_BASE}/api/sessions/${sessionId}/stream`, async (): Promise<Record<string, string>> => {
    const token = getTrialToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  });
}

export function connectTrialSSE(
  sessionId: string,
  onEvent: (event: Record<string, unknown>) => void,
  onConnectionChange?: (connected: boolean) => void
): () => void {
  return subscribeToSessionEvents(createTrialSSEConnection(sessionId), onEvent, onConnectionChange);
}

export async function convertTrialAccount(params: {
  trial_token: string;
  password: string;
  name?: string;
}): Promise<{ status: string; email: string; name: string | null }> {
  const res = await apiFetch(`${API_BASE}/api/free-trial/convert`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) await throwApiError(res);
  return res.json();
}

// Copyright (c) 2026 V2 Software LLC. All rights reserved.

/**
 * API client for the JobHunter Agent backend.
 * Handles REST calls, SSE streaming, and WebSocket connections.
 */

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

// ---------- Types ----------

export interface SearchConfig {
  keywords: string[];
  locations: string[];
  remote_only: boolean;
  salary_min: number | null;
  search_radius: number;
  experience_level: string | null;
  job_type: string | null;
}

export interface JobListing {
  id: string;
  title: string;
  company: string;
  location: string;
  url: string;
  board: string;
  ats_type: string;
  salary_range: string | null;
  description_snippet: string | null;
  is_remote: boolean;
}

export interface ScoredJob {
  job: JobListing;
  score: number;
  score_breakdown: Record<string, number>;
  reasons: string[];
}

export interface ResumeScore {
  overall: number;
  keyword_density: number;
  impact_metrics: number;
  ats_compatibility: number;
  readability: number;
  formatting: number;
  feedback: string[];
}

export interface CoachOutput {
  rewritten_resume: string;
  resume_score: ResumeScore;
  cover_letter_template: string;
  linkedin_advice: string[];
  confidence_message: string;
  key_strengths: string[];
  improvement_areas: string[];
}

export interface ApplicationResult {
  job_id: string;
  status: "queued" | "in_progress" | "submitted" | "failed" | "skipped";
  screenshot_url: string | null;
  error_message: string | null;
  duration_seconds: number | null;
}

export interface SessionSummary {
  session_id: string;
  total_discovered: number;
  total_scored: number;
  total_applied: number;
  total_failed: number;
  total_skipped: number;
  top_companies: string[];
  avg_fit_score: number;
  resume_score: ResumeScore | null;
  duration_minutes: number;
  next_steps: string[];
}

export type SSEEventType =
  | "status"
  | "coaching"
  | "coach_review"
  | "coaching_progress"
  | "discovery"
  | "discovery_progress"
  | "scoring"
  | "scoring_progress"
  | "tailoring"
  | "tailoring_progress"
  | "shortlist_review"
  | "agent_complete"
  | "hitl"
  | "application_progress"
  | "application_browser_action"
  | "verification_progress"
  | "backfill_progress"
  | "reporting_progress"
  | "needs_intervention"
  | "ready_to_submit"
  | "login_required"
  | "login_complete"
  | "captcha_detected"
  | "done"
  | "error"
  | "ping";

export interface SSEEvent {
  type: SSEEventType;
  data: Record<string, unknown>;
}

// ---------- CSRF helpers ----------

function getCsrfToken(): string {
  if (typeof document === "undefined") return "";
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : "";
}

function csrfHeaders(): Record<string, string> {
  const token = getCsrfToken();
  return token ? { "x-csrf-token": token } : {};
}

// ---------- Auth helpers ----------

let _cachedToken: string | null = null;
let _tokenFetchedAt = 0;
const _TOKEN_TTL_MS = 5 * 60 * 1000; // 5 minutes

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

/**
 * Get a raw JWT token string for use in SSE query params.
 * EventSource cannot send headers, so we pass ?token=<jwt>.
 */
export async function getSSEToken(): Promise<string> {
  if (_cachedToken && Date.now() - _tokenFetchedAt < _TOKEN_TTL_MS) {
    return _cachedToken;
  }
  try {
    const res = await fetch("/api/auth/token");
    if (res.ok) {
      const { token } = await res.json();
      if (token) {
        _cachedToken = token;
        _tokenFetchedAt = Date.now();
        return token;
      }
    }
  } catch {}
  return "";
}

// ---------- Fetch wrapper (surfaces 429 to user) ----------

import { toast } from "sonner";

let _lastRateLimitToast = 0;

/**
 * Wrapper around fetch that shows a user-visible toast on 429 responses
 * so rate-limit errors aren't silently swallowed.
 */
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

// ---------- REST API ----------

export async function startSession(params: {
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
    ai_temperature?: number;
    scoring_strictness?: number;
  };
}): Promise<{ session_id: string }> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(`${API_BASE}/api/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {}
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return res.json();
}

export interface SessionListItem {
  session_id: string;
  status: string;
  keywords: string[];
  locations: string[];
  remote_only: boolean;
  salary_min: number | null;
  resume_text_snippet: string;
  linkedin_url: string | null;
  applications_submitted: number;
  applications_failed: number;
  created_at: string;
  archived_at: string | null;
}

export interface ResumeAnalysis {
  keywords: string[];
  locations: string[];
  experience_level: string | null;
  suggested_job_boards: string[];
  remote_likely: boolean;
}

export async function analyzeResume(resumeText: string): Promise<ResumeAnalysis> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(`${API_BASE}/api/resume/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify({ resume_text: resumeText }),
  });
  if (!res.ok) throw new Error(`Failed to analyze resume: ${res.statusText}`);
  return res.json();
}

export interface LifetimeStats {
  total_sessions: number;
  total_submitted: number;
  total_failed: number;
  total_applications: number;
  manual_estimate_minutes: number;
  automation_minutes: number;
  time_saved_minutes: number;
  time_saved_hours: number;
}

export async function getLifetimeStats(): Promise<LifetimeStats> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(`${API_BASE}/api/stats/lifetime`, { headers: auth });
  if (!res.ok) throw new Error(`Failed to get lifetime stats: ${res.statusText}`);
  return res.json();
}

export async function listSessions(includeArchived?: boolean): Promise<SessionListItem[]> {
  const auth = await getAuthHeaders();
  const qs = includeArchived ? "?include_archived=true" : "";
  const res = await apiFetch(`${API_BASE}/api/sessions${qs}`, { headers: auth });
  if (!res.ok) throw new Error(`Failed to list sessions: ${res.statusText}`);
  const sessions: SessionListItem[] = await res.json();
  return sessions.map((s) => ({ ...s, keywords: s.keywords || [], locations: s.locations || [] }));
}

export async function archiveSession(sessionId: string, archived: boolean): Promise<void> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(`${API_BASE}/api/sessions/${sessionId}/archive`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify({ archived }),
  });
  if (!res.ok) throw new Error(`Failed to ${archived ? "archive" : "unarchive"} session: ${res.statusText}`);
}

export async function deleteSession(sessionId: string): Promise<void> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(`${API_BASE}/api/sessions/${sessionId}`, {
    method: "DELETE",
    headers: auth,
  });
  if (!res.ok) throw new Error(`Failed to delete session: ${res.statusText}`);
}

export async function getSession(sessionId: string): Promise<Record<string, unknown>> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(`${API_BASE}/api/sessions/${sessionId}`, { headers: auth });
  if (!res.ok) throw new Error(`Failed to get session: ${res.statusText}`);
  return res.json();
}

export async function getSkippedJobs(sessionId: string): Promise<{ skipped_jobs: SkippedJob[] }> {
  const res = await apiFetch(`${API_BASE}/api/sessions/${sessionId}/skipped-jobs`);
  if (!res.ok) throw new Error(`Failed to get skipped jobs: ${res.statusText}`);
  return res.json();
}

export type SkippedJob = {
  job: {
    id: string;
    title: string;
    company: string;
    location: string;
    url: string;
    board: string;
  };
  score: number;
  tailored_resume: {
    tailored_text: string;
    fit_score: number;
    changes_made: string[];
  } | null;
  cover_letter_template: string;
};

export type ApplicationLogEntry = {
  status: "submitted" | "failed" | "skipped";
  job: {
    id?: string;
    title?: string;
    company?: string;
    location?: string;
    url?: string;
    board?: string;
  };
  error: string | null;
  cover_letter: string;
  tailored_resume: {
    tailored_text: string;
    fit_score: number;
    changes_made: string[];
  } | null;
  duration: number | null;
  submitted_at: string | null;
  screenshot_path: string | null;
};

export async function getApplicationLog(
  sessionId: string
): Promise<{ entries: ApplicationLogEntry[] }> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(`${API_BASE}/api/sessions/${sessionId}/application-log`, { headers: auth });
  if (!res.ok) throw new Error(`Failed to get application log: ${res.statusText}`);
  return res.json();
}

export async function sendSteer(
  sessionId: string,
  data: { message: string; mode?: string }
): Promise<{
  status: string;
  message: string;
  directives: Record<string, unknown>[];
}> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(`${API_BASE}/api/sessions/${sessionId}/steer`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Failed to send steer: ${res.statusText}`);
  return res.json();
}

export async function sendCoachChat(
  sessionId: string,
  data: { message: string }
): Promise<{
  status: string;
  message: string;
  coach_output: CoachOutput;
  coach_chat_history: Array<{ role: string; text: string }>;
}> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(`${API_BASE}/api/sessions/${sessionId}/coach-chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Failed to send coach chat: ${res.statusText}`);
  return res.json();
}

export async function submitCoachReview(
  sessionId: string,
  data: { approved: boolean; edited_resume?: string; feedback?: string }
): Promise<void> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(`${API_BASE}/api/sessions/${sessionId}/coach-review`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Failed to submit coach review: ${res.statusText}`);
}

export async function submitReview(
  sessionId: string,
  data: { approved_job_ids: string[]; feedback: string }
): Promise<void> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(`${API_BASE}/api/sessions/${sessionId}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Failed to submit review: ${res.statusText}`);
}

export async function submitDecision(
  sessionId: string,
  decision: "submit" | "skip"
): Promise<void> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(`${API_BASE}/api/sessions/${sessionId}/submit-decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify({ decision }),
  });
  if (!res.ok) throw new Error(`Failed to submit decision: ${res.status}`);
}

export async function resumeIntervention(sessionId: string): Promise<void> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(`${API_BASE}/api/sessions/${sessionId}/resume-intervention`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...auth },
  });
  if (!res.ok) throw new Error(`Failed to resume intervention: ${res.status}`);
}

// ---------- Pre-login confirmation ----------

export async function confirmLogin(sessionId: string): Promise<void> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(`${API_BASE}/api/sessions/${sessionId}/login-complete`, {
    method: "POST",
    headers: auth,
  });
  if (!res.ok) throw new Error(`Failed to confirm login: ${res.status}`);
}

// ---------- Resume stalled pipeline ----------

export async function resumeSession(
  sessionId: string
): Promise<{ status: string; next: string[]; action: string }> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(`${API_BASE}/api/sessions/${sessionId}/resume`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...auth },
  });
  if (!res.ok) throw new Error(`Failed to resume session: ${res.statusText}`);
  return res.json();
}

// ---------- Rewind ----------

export interface Checkpoint {
  checkpoint_id: string;
  status: string;
  applications_submitted: number;
  applications_failed: number;
  application_queue: number;
}

export async function listCheckpoints(sessionId: string): Promise<Checkpoint[]> {
  const res = await apiFetch(`${API_BASE}/api/sessions/${sessionId}/checkpoints`);
  if (!res.ok) throw new Error(`Failed to list checkpoints: ${res.statusText}`);
  const data = await res.json();
  return data.checkpoints;
}

export async function rewindSession(
  sessionId: string,
  checkpointId: string,
  approvedJobIds?: string[]
): Promise<{ status: string; message: string }> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(`${API_BASE}/api/sessions/${sessionId}/rewind`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify({
      checkpoint_id: checkpointId,
      approved_job_ids: approvedJobIds,
    }),
  });
  if (!res.ok) throw new Error(`Failed to rewind session: ${res.statusText}`);
  return res.json();
}

// ---------- SSE ----------

export async function createSSEConnection(sessionId: string): Promise<EventSource> {
  const token = await getSSEToken();
  const sep = token ? `?token=${encodeURIComponent(token)}` : "";
  return new EventSource(`${API_BASE}/api/sessions/${sessionId}/stream${sep}`);
}

/**
 * Connect to SSE and call onEvent for each parsed event.
 * Returns a cleanup function.
 */
export function connectSSE(
  sessionId: string,
  onEvent: (event: Record<string, unknown>) => void,
  onConnectionChange?: (connected: boolean) => void
): () => void {
  let es: EventSource | null = null;
  let cancelled = false;

  const EVENT_TYPES: SSEEventType[] = [
    "status",
    "coaching",
    "coach_review",
    "coaching_progress",
    "discovery",
    "discovery_progress",
    "scoring",
    "scoring_progress",
    "tailoring",
    "tailoring_progress",
    "shortlist_review",
    "agent_complete",
    "hitl",
    "application_progress",
    "application_browser_action",
    "verification_progress",
    "backfill_progress",
    "reporting_progress",
    "needs_intervention",
    "ready_to_submit",
    "login_required",
    "login_complete",
    "captcha_detected",
    "done",
    "error",
  ];

  createSSEConnection(sessionId).then((source) => {
    if (cancelled) {
      source.close();
      return;
    }
    es = source;

    es.onopen = () => {
      onConnectionChange?.(true);
    };

    es.onerror = () => {
      // EventSource auto-reconnects; signal disconnected state
      if (es?.readyState === EventSource.CLOSED) {
        onConnectionChange?.(false);
      } else if (es?.readyState === EventSource.CONNECTING) {
        onConnectionChange?.(false);
      }
    };

    for (const eventType of EVENT_TYPES) {
      es.addEventListener(eventType, (e: Event) => {
        try {
          const me = e as MessageEvent;
          const data = JSON.parse(me.data);
          onEvent({
            ...data,
            event: eventType,
            timestamp: data.timestamp || new Date().toISOString(),
          });
          if (eventType === "done") {
            es?.close();
          }
        } catch {
          // ignore parse errors
        }
      });
    }

    es.onmessage = (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        onEvent({
          ...data,
          event: data.event || "message",
          timestamp: data.timestamp || new Date().toISOString(),
        });
      } catch {
        // ignore parse errors
      }
    };
  });

  return () => {
    cancelled = true;
    es?.close();
  };
}

// ---------- Resume Parsing ----------

export async function parseResume(
  file: File
): Promise<{ text: string; filename: string; file_path?: string; resume_uuid?: string }> {
  const auth = await getAuthHeaders();
  const form = new FormData();
  form.append("file", file);
  const res = await apiFetch(`${API_BASE}/api/sessions/parse-resume`, {
    method: "POST",
    headers: auth,
    body: form,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail || `Failed to parse resume: ${res.statusText}`);
  }
  return res.json();
}

// ---------- LinkedIn Profile Updater ----------

export interface LinkedInUpdate {
  section: string;
  content: string;
}

export async function startLinkedInUpdate(
  sessionId: string,
  updates: LinkedInUpdate[],
  linkedinUrl?: string
): Promise<{ status: string; message: string }> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(`${API_BASE}/api/sessions/${sessionId}/linkedin-update`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify({ updates, linkedin_url: linkedinUrl }),
  });
  if (!res.ok) throw new Error(`LinkedIn update failed: ${res.statusText}`);
  return res.json();
}

// ---------- Billing API ----------

export async function getWallet(): Promise<{
  balance: number;
  free_remaining: number;
  application_cost: number;
  is_premium?: boolean;
}> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(`${API_BASE}/api/billing/wallet`, { headers: auth });
  if (!res.ok) throw new Error("Failed to fetch wallet");
  return res.json();
}

export async function getTransactions(): Promise<{
  transactions: Array<{
    id: string;
    amount: number;
    balance_after: number;
    type: string;
    description: string;
    created_at: string | null;
  }>;
}> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(`${API_BASE}/api/billing/transactions`, { headers: auth });
  if (!res.ok) throw new Error("Failed to fetch transactions");
  return res.json();
}

export async function updateAutoRefill(settings: {
  enabled: boolean;
  threshold: number;
  pack_id: string;
}): Promise<{ ok: boolean }> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(`${API_BASE}/api/billing/auto-refill`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify(settings),
  });
  if (!res.ok) throw new Error("Failed to update auto-refill settings");
  return res.json();
}

export async function createCheckout(packId: string): Promise<{ url: string }> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(`${API_BASE}/api/billing/checkout`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify({ pack_id: packId }),
  });
  if (!res.ok) throw new Error("Failed to create checkout");
  return res.json();
}

// ---------- Autopilot ----------

export interface AutopilotSchedule {
  id: string;
  name: string;
  keywords: string[];
  locations: string[];
  remote_only: boolean;
  salary_min: number | null;
  search_radius: number;
  cron_expression: string;
  timezone: string;
  is_active: boolean;
  auto_approve: boolean;
  notification_email: string | null;
  last_run_at: string | null;
  next_run_at: string | null;
  last_session_id: string | null;
  created_at: string;
}

export async function listAutopilotSchedules(): Promise<AutopilotSchedule[]> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(`${API_BASE}/api/autopilot/schedules`, { headers: auth });
  if (!res.ok) throw new Error("Failed to list autopilot schedules");
  return res.json();
}

export async function createAutopilotSchedule(params: {
  name: string;
  keywords: string[];
  locations: string[];
  remote_only?: boolean;
  salary_min?: number | null;
  search_radius?: number;
  resume_text?: string | null;
  linkedin_url?: string | null;
  session_config?: Record<string, unknown>;
  cron_expression?: string;
  timezone?: string;
  auto_approve?: boolean;
}): Promise<AutopilotSchedule> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(`${API_BASE}/api/autopilot/schedules`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error("Failed to create autopilot schedule");
  return res.json();
}

export async function updateAutopilotSchedule(
  id: string,
  updates: Partial<AutopilotSchedule>
): Promise<AutopilotSchedule> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(`${API_BASE}/api/autopilot/schedules/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify(updates),
  });
  if (!res.ok) throw new Error("Failed to update autopilot schedule");
  return res.json();
}

export async function deleteAutopilotSchedule(id: string): Promise<void> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(`${API_BASE}/api/autopilot/schedules/${id}`, {
    method: "DELETE",
    headers: auth,
  });
  if (!res.ok) throw new Error("Failed to delete autopilot schedule");
}

export async function toggleAutopilotPause(id: string): Promise<AutopilotSchedule> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(`${API_BASE}/api/autopilot/schedules/${id}/pause`, {
    method: "POST",
    headers: auth,
  });
  if (!res.ok) throw new Error("Failed to toggle autopilot pause");
  return res.json();
}

export async function triggerAutopilotNow(id: string): Promise<{ triggered: boolean }> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(`${API_BASE}/api/autopilot/schedules/${id}/run-now`, {
    method: "POST",
    headers: auth,
  });
  if (!res.ok) throw new Error("Failed to trigger autopilot run");
  return res.json();
}

// ---------- Free Trial ----------

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
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {}
    throw new Error(detail || `Request failed (${res.status})`);
  }
  const data = await res.json();
  setTrialData(data.trial_token, data.email);
  return data;
}

export function createTrialSSEConnection(sessionId: string): EventSource {
  const token = getTrialToken();
  const sep = token ? `?token=${encodeURIComponent(token)}` : "";
  return new EventSource(`${API_BASE}/api/sessions/${sessionId}/stream${sep}`);
}

export function connectTrialSSE(
  sessionId: string,
  onEvent: (event: Record<string, unknown>) => void,
  onConnectionChange?: (connected: boolean) => void
): () => void {
  let es: EventSource | null = null;
  let cancelled = false;

  const EVENT_TYPES: SSEEventType[] = [
    "status", "coaching", "coach_review", "coaching_progress",
    "discovery", "discovery_progress", "scoring", "scoring_progress",
    "tailoring", "tailoring_progress", "shortlist_review", "agent_complete",
    "hitl", "application_progress", "application_browser_action",
    "verification_progress", "backfill_progress", "reporting_progress",
    "needs_intervention", "ready_to_submit", "login_required",
    "login_complete", "captcha_detected", "done", "error",
  ];

  const source = createTrialSSEConnection(sessionId);
  es = source;

  es.onopen = () => onConnectionChange?.(true);
  es.onerror = () => {
    if (es?.readyState === EventSource.CLOSED) onConnectionChange?.(false);
    else if (es?.readyState === EventSource.CONNECTING) onConnectionChange?.(false);
  };

  for (const eventType of EVENT_TYPES) {
    es.addEventListener(eventType, (e: Event) => {
      if (cancelled) return;
      try {
        const me = e as MessageEvent;
        const data = JSON.parse(me.data);
        onEvent({
          ...data,
          event: eventType,
          timestamp: data.timestamp || new Date().toISOString(),
        });
        if (eventType === "done") es?.close();
      } catch {}
    });
  }

  es.onmessage = (e: MessageEvent) => {
    if (cancelled) return;
    try {
      const data = JSON.parse(e.data);
      onEvent({
        ...data,
        event: data.event || "message",
        timestamp: data.timestamp || new Date().toISOString(),
      });
    } catch {}
  };

  return () => {
    cancelled = true;
    es?.close();
  };
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
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {}
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return res.json();
}

// ---------- Marketplace ----------

export interface MarketplaceAgent {
  id: string;
  slug: string;
  name: string;
  description: string;
  long_description: string | null;
  icon: string;
  category: string;
  credit_cost: number;
  is_builtin: boolean;
  total_uses: number;
  avg_rating: number;
  rating_count: number;
  frontend_path: string;
  stages: { name: string; description: string }[];
  created_at: string;
}

export interface AgentReview {
  id: string;
  rating: number;
  review_text: string | null;
  user_name: string;
  created_at: string;
}

export async function listMarketplaceAgents(
  category?: string
): Promise<MarketplaceAgent[]> {
  const params = category ? `?category=${encodeURIComponent(category)}` : "";
  const res = await apiFetch(`${API_BASE}/api/marketplace/agents${params}`);
  if (!res.ok) throw new Error("Failed to load agents");
  const data = await res.json();
  return data.agents;
}

export async function getMarketplaceAgent(
  slug: string
): Promise<{ agent: MarketplaceAgent; reviews: AgentReview[] }> {
  const res = await apiFetch(`${API_BASE}/api/marketplace/agents/${slug}`);
  if (!res.ok) throw new Error("Agent not found");
  return res.json();
}

export async function submitAgentReview(
  slug: string,
  rating: number,
  reviewText?: string,
  sessionId?: string
): Promise<void> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(`${API_BASE}/api/marketplace/agents/${slug}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify({
      rating,
      review_text: reviewText || null,
      session_id: sessionId || null,
    }),
  });
  if (!res.ok) throw new Error("Failed to submit review");
}

export async function listAgentReviews(
  slug: string,
  limit = 20,
  offset = 0
): Promise<AgentReview[]> {
  const res = await apiFetch(
    `${API_BASE}/api/marketplace/agents/${slug}/reviews?limit=${limit}&offset=${offset}`
  );
  if (!res.ok) throw new Error("Failed to load reviews");
  const data = await res.json();
  return data.reviews;
}

// ---------- Developer Platform ----------

export interface ApiKey {
  id: string;
  key?: string; // Only present on creation
  key_prefix: string;
  name: string;
  is_active: boolean;
  last_used_at: string | null;
  created_at: string;
}

export interface Webhook {
  id: string;
  url: string;
  secret: string;
  events: string[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface WebhookDelivery {
  id: string;
  event_type: string;
  payload: Record<string, unknown>;
  response_status: number | null;
  response_body: string | null;
  success: boolean;
  delivered_at: string;
}

export async function createApiKey(name: string): Promise<ApiKey> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(`${API_BASE}/api/developer/api-keys`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error("Failed to create API key");
  const data = await res.json();
  return data.api_key;
}

export async function listApiKeys(): Promise<ApiKey[]> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(`${API_BASE}/api/developer/api-keys`, { headers: auth });
  if (!res.ok) throw new Error("Failed to load API keys");
  const data = await res.json();
  return data.api_keys;
}

export async function revokeApiKey(keyId: string): Promise<void> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(`${API_BASE}/api/developer/api-keys/${keyId}`, {
    method: "DELETE",
    headers: auth,
  });
  if (!res.ok) throw new Error("Failed to revoke API key");
}

export async function createWebhook(
  url: string,
  events: string[]
): Promise<Webhook> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(`${API_BASE}/api/developer/webhooks`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify({ url, events }),
  });
  if (!res.ok) throw new Error("Failed to create webhook");
  const data = await res.json();
  return data.webhook;
}

export async function listWebhooks(): Promise<Webhook[]> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(`${API_BASE}/api/developer/webhooks`, { headers: auth });
  if (!res.ok) throw new Error("Failed to load webhooks");
  const data = await res.json();
  return data.webhooks;
}

export async function deleteWebhook(webhookId: string): Promise<void> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(`${API_BASE}/api/developer/webhooks/${webhookId}`, {
    method: "DELETE",
    headers: auth,
  });
  if (!res.ok) throw new Error("Failed to delete webhook");
}

export async function listWebhookDeliveries(
  webhookId: string,
  limit = 20
): Promise<WebhookDelivery[]> {
  const auth = await getAuthHeaders();
  const res = await apiFetch(
    `${API_BASE}/api/developer/webhooks/${webhookId}/deliveries?limit=${limit}`,
    { headers: auth }
  );
  if (!res.ok) throw new Error("Failed to load deliveries");
  const data = await res.json();
  return data.deliveries;
}

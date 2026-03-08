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

// ---------- REST API ----------

export async function startSession(params: {
  keywords: string[];
  locations: string[];
  remote_only: boolean;
  salary_min: number | null;
  search_radius?: number;
  resume_text: string | null;
  resume_file_path: string | null;
  linkedin_url: string | null;
  preferences: Record<string, unknown>;
  config?: {
    max_jobs: number;
    tailoring_quality: string;
    application_mode: string;
    generate_cover_letters: boolean;
    job_boards: string[];
  };
}): Promise<{ session_id: string }> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_BASE}/api/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(`Failed to start session: ${res.statusText}`);
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
  const res = await fetch(`${API_BASE}/api/resume/analyze`, {
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
  const res = await fetch(`${API_BASE}/api/stats/lifetime`, { headers: auth });
  if (!res.ok) throw new Error(`Failed to get lifetime stats: ${res.statusText}`);
  return res.json();
}

export async function listSessions(): Promise<SessionListItem[]> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_BASE}/api/sessions`, { headers: auth });
  if (!res.ok) throw new Error(`Failed to list sessions: ${res.statusText}`);
  return res.json();
}

export async function getSession(
  sessionId: string
): Promise<Record<string, unknown>> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}`, { headers: auth });
  if (!res.ok) throw new Error(`Failed to get session: ${res.statusText}`);
  return res.json();
}

export async function getSkippedJobs(
  sessionId: string
): Promise<{ skipped_jobs: SkippedJob[] }> {
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/skipped-jobs`);
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
  const res = await fetch(
    `${API_BASE}/api/sessions/${sessionId}/application-log`
  );
  if (!res.ok)
    throw new Error(`Failed to get application log: ${res.statusText}`);
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
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/steer`, {
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
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/coach-chat`, {
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
  const res = await fetch(
    `${API_BASE}/api/sessions/${sessionId}/coach-review`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...auth },
      body: JSON.stringify(data),
    }
  );
  if (!res.ok)
    throw new Error(`Failed to submit coach review: ${res.statusText}`);
}

export async function submitReview(
  sessionId: string,
  data: { approved_job_ids: string[]; feedback: string }
): Promise<void> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/review`, {
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
  const res = await fetch(
    `${API_BASE}/api/sessions/${sessionId}/submit-decision`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...auth },
      body: JSON.stringify({ decision }),
    }
  );
  if (!res.ok) throw new Error(`Failed to submit decision: ${res.status}`);
}

export async function resumeIntervention(sessionId: string): Promise<void> {
  const auth = await getAuthHeaders();
  const res = await fetch(
    `${API_BASE}/api/sessions/${sessionId}/resume-intervention`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...auth },
    }
  );
  if (!res.ok) throw new Error(`Failed to resume intervention: ${res.status}`);
}

// ---------- Pre-login confirmation ----------

export async function confirmLogin(sessionId: string): Promise<void> {
  const auth = await getAuthHeaders();
  const res = await fetch(
    `${API_BASE}/api/sessions/${sessionId}/login-complete`,
    { method: "POST", headers: auth }
  );
  if (!res.ok) throw new Error(`Failed to confirm login: ${res.status}`);
}

// ---------- Resume stalled pipeline ----------

export async function resumeSession(
  sessionId: string
): Promise<{ status: string; next: string[]; action: string }> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/resume`, {
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

export async function listCheckpoints(
  sessionId: string
): Promise<Checkpoint[]> {
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/checkpoints`);
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
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/rewind`, {
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

export function createSSEConnection(sessionId: string): EventSource {
  return new EventSource(`${API_BASE}/api/sessions/${sessionId}/stream`);
}

/**
 * Connect to SSE and call onEvent for each parsed event.
 * Returns a cleanup function.
 */
export function connectSSE(
  sessionId: string,
  onEvent: (event: Record<string, unknown>) => void
): () => void {
  const es = createSSEConnection(sessionId);

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
    "reporting_progress",
    "needs_intervention",
    "ready_to_submit",
    "login_required",
    "login_complete",
    "captcha_detected",
    "done",
    "error",
  ];

  for (const eventType of EVENT_TYPES) {
    es.addEventListener(eventType, (e: Event) => {
      try {
        const me = e as MessageEvent;
        const data = JSON.parse(me.data);
        // Enrich with event type and timestamp so the UI can display them
        onEvent({
          ...data,
          event: eventType,
          timestamp: data.timestamp || new Date().toISOString(),
        });
        // Close EventSource on terminal event to prevent auto-reconnect
        // (EventSource auto-reconnects when the stream ends, causing
        // infinite replay loops for completed/failed sessions)
        if (eventType === "done") {
          es.close();
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

  return () => es.close();
}

// ---------- Resume Parsing ----------

export async function parseResume(
  file: File
): Promise<{ text: string; filename: string; file_path?: string }> {
  const auth = await getAuthHeaders();
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/sessions/parse-resume`, {
    method: "POST",
    headers: auth,
    body: form,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(
      detail?.detail || `Failed to parse resume: ${res.statusText}`
    );
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
  const res = await fetch(
    `${API_BASE}/api/sessions/${sessionId}/linkedin-update`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...auth },
      body: JSON.stringify({ updates, linkedin_url: linkedinUrl }),
    }
  );
  if (!res.ok) throw new Error(`LinkedIn update failed: ${res.statusText}`);
  return res.json();
}

// ---------- Billing API ----------

export async function getWallet(): Promise<{
  balance: number;
  free_remaining: number;
  application_cost: number;
}> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_BASE}/api/billing/wallet`, { headers: auth });
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
  const res = await fetch(`${API_BASE}/api/billing/transactions`, { headers: auth });
  if (!res.ok) throw new Error("Failed to fetch transactions");
  return res.json();
}

export async function updateAutoRefill(settings: {
  enabled: boolean;
  threshold: number;
  pack_id: string;
}): Promise<{ ok: boolean }> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_BASE}/api/billing/auto-refill`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify(settings),
  });
  if (!res.ok) throw new Error("Failed to update auto-refill settings");
  return res.json();
}

export async function createCheckout(packId: string): Promise<{ url: string }> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_BASE}/api/billing/checkout`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify({ pack_id: packId }),
  });
  if (!res.ok) throw new Error("Failed to create checkout");
  return res.json();
}

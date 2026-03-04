/**
 * API client for the JobHunter Agent backend.
 * Handles REST calls, SSE streaming, and WebSocket connections.
 */

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  (typeof window !== "undefined" && window.location.port === "3000"
    ? "http://localhost:8000"
    : "");

// ---------- Types ----------

export interface SearchConfig {
  keywords: string[];
  locations: string[];
  remote_only: boolean;
  salary_min: number | null;
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
  | "discovery"
  | "scoring"
  | "tailoring"
  | "agent_complete"
  | "hitl"
  | "application_progress"
  | "done"
  | "error"
  | "ping";

export interface SSEEvent {
  type: SSEEventType;
  data: Record<string, unknown>;
}

// ---------- REST API ----------

export async function startSession(params: {
  keywords: string[];
  locations: string[];
  remote_only: boolean;
  salary_min: number | null;
  resume_text: string | null;
  linkedin_url: string | null;
  preferences: Record<string, unknown>;
}): Promise<{ session_id: string }> {
  const res = await fetch(`${API_BASE}/api/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(`Failed to start session: ${res.statusText}`);
  return res.json();
}

export async function getSession(sessionId: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}`);
  if (!res.ok) throw new Error(`Failed to get session: ${res.statusText}`);
  return res.json();
}

export async function sendSteer(
  sessionId: string,
  data: { message: string; mode?: string }
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/steer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Failed to send steer: ${res.statusText}`);
}

export async function submitReview(
  sessionId: string,
  data: { approved_job_ids: string[]; feedback: string }
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Failed to submit review: ${res.statusText}`);
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

  const handler = (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data);
      onEvent(data);
    } catch {
      // ignore parse errors
    }
  };

  es.addEventListener("status", handler);
  es.addEventListener("coaching", handler);
  es.addEventListener("discovery", handler);
  es.addEventListener("scoring", handler);
  es.addEventListener("tailoring", handler);
  es.addEventListener("agent_complete", handler);
  es.addEventListener("hitl", handler);
  es.addEventListener("application_progress", handler);
  es.addEventListener("done", handler);
  es.addEventListener("error", handler);
  es.onmessage = handler;

  return () => es.close();
}

// ---------- WebSocket (for Phase 3: screenshot feed + chat) ----------

export function createWebSocket(sessionId: string): WebSocket {
  const wsBase = API_BASE.replace(/^http/, "ws");
  return new WebSocket(`${wsBase}/ws/sessions/${sessionId}`);
}

/**
 * Connect to WebSocket for screenshot feed + chat.
 * Returns a cleanup function.
 */
export function connectWebSocket(
  sessionId: string,
  onMessage: (data: Record<string, unknown>) => void
): () => void {
  const ws = createWebSocket(sessionId);

  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      onMessage(data);
    } catch {
      // ignore parse errors
    }
  };

  ws.onerror = (err) => console.error("WebSocket error:", err);

  return () => {
    if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
      ws.close();
    }
  };
}

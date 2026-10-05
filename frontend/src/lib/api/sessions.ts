// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { API_BASE } from "./config";
import { apiFetch, authenticatedFetch, throwApiError } from "./transport";
import type { CoachOutput } from "./types";

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
    minimum_submitted_applications?: number;
    tailoring_quality: string;
    application_mode: string;
    generate_cover_letters: boolean;
    job_boards: string[];
    ai_temperature?: number;
    scoring_strictness?: number;
    discovery_mode?: string;
    job_urls?: string[];
  };
  job_urls?: string[];
}): Promise<{ session_id: string }> {
  const res = await authenticatedFetch(`${API_BASE}/api/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) await throwApiError(res);
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
  applications_uncertain?: number;
  created_at: string;
  archived_at: string | null;
  is_autopilot?: boolean;
}

export interface LifetimeStats {
  total_sessions: number;
  total_submitted: number;
  total_failed: number;
  total_uncertain?: number;
  total_applications: number;
  manual_estimate_minutes: number;
  automation_minutes: number;
  time_saved_minutes: number;
  time_saved_hours: number;
}

export async function getLifetimeStats(): Promise<LifetimeStats> {
  const res = await authenticatedFetch(`${API_BASE}/api/stats/lifetime`, {});
  if (!res.ok) throw new Error(`Failed to get lifetime stats: ${res.statusText}`);
  return res.json();
}

export async function listSessions(includeArchived?: boolean): Promise<SessionListItem[]> {
  const qs = includeArchived ? "?include_archived=true" : "";
  const res = await authenticatedFetch(`${API_BASE}/api/sessions${qs}`, {});
  if (!res.ok) throw new Error(`Failed to list sessions: ${res.statusText}`);
  const sessions: SessionListItem[] = await res.json();
  return sessions.map((s) => ({ ...s, keywords: s.keywords || [], locations: s.locations || [] }));
}

export async function rerunSession(
  sessionId: string,
  overrides?: {
    keywords?: string[];
    locations?: string[];
    remote_only?: boolean;
    salary_min?: number | null;
  }
): Promise<{ session_id: string }> {
  const res = await authenticatedFetch(`${API_BASE}/api/sessions/${sessionId}/rerun`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(overrides || {}),
  });
  if (!res.ok) await throwApiError(res);
  return res.json();
}

export async function killSession(sessionId: string): Promise<{ status: string }> {
  const res = await authenticatedFetch(`${API_BASE}/api/sessions/${sessionId}/kill`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) await throwApiError(res);
  return res.json();
}

export async function archiveSession(sessionId: string, archived: boolean): Promise<void> {
  const res = await authenticatedFetch(`${API_BASE}/api/sessions/${sessionId}/archive`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ archived }),
  });
  if (!res.ok) throw new Error(`Failed to ${archived ? "archive" : "unarchive"} session: ${res.statusText}`);
}

export async function deleteSession(sessionId: string): Promise<void> {
  const res = await authenticatedFetch(`${API_BASE}/api/sessions/${sessionId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`Failed to delete session: ${res.statusText}`);
}

export async function getSession(sessionId: string): Promise<Record<string, unknown>> {
  const res = await authenticatedFetch(`${API_BASE}/api/sessions/${sessionId}`, {});
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
  error_category?: string | null;
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
  const res = await authenticatedFetch(`${API_BASE}/api/sessions/${sessionId}/application-log`, {});
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
  const res = await authenticatedFetch(`${API_BASE}/api/sessions/${sessionId}/steer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
  const res = await authenticatedFetch(`${API_BASE}/api/sessions/${sessionId}/coach-chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Failed to send coach chat: ${res.statusText}`);
  return res.json();
}

export async function submitCoachReview(
  sessionId: string,
  data: { approved: boolean; edited_resume?: string; use_original?: boolean; feedback?: string }
): Promise<void> {
  const res = await authenticatedFetch(`${API_BASE}/api/sessions/${sessionId}/coach-review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Failed to submit coach review: ${res.statusText}`);
}

export async function submitReview(
  sessionId: string,
  data: { approved_job_ids: string[]; feedback: string }
): Promise<void> {
  const res = await authenticatedFetch(`${API_BASE}/api/sessions/${sessionId}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Failed to submit review: ${res.statusText}`);
}

export async function submitDecision(
  sessionId: string,
  decision: "submit" | "skip"
): Promise<void> {
  const res = await authenticatedFetch(`${API_BASE}/api/sessions/${sessionId}/submit-decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision }),
  });
  if (!res.ok) throw new Error(`Failed to submit decision: ${res.status}`);
}

export async function resumeIntervention(sessionId: string): Promise<void> {
  const res = await authenticatedFetch(`${API_BASE}/api/sessions/${sessionId}/resume-intervention`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error(`Failed to resume intervention: ${res.status}`);
}

export async function confirmLogin(sessionId: string): Promise<void> {
  const res = await authenticatedFetch(`${API_BASE}/api/sessions/${sessionId}/login-complete`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`Failed to confirm login: ${res.status}`);
}

export async function resumeSession(
  sessionId: string
): Promise<{ status: string; next: string[]; action: string }> {
  const res = await authenticatedFetch(`${API_BASE}/api/sessions/${sessionId}/resume`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error(`Failed to resume session: ${res.statusText}`);
  return res.json();
}

export interface Checkpoint {
  checkpoint_id: string;
  status: string;
  applications_submitted: number;
  applications_failed: number;
  applications_uncertain?: number;
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
  const res = await authenticatedFetch(`${API_BASE}/api/sessions/${sessionId}/rewind`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      checkpoint_id: checkpointId,
      approved_job_ids: approvedJobIds,
    }),
  });
  if (!res.ok) throw new Error(`Failed to rewind session: ${res.statusText}`);
  return res.json();
}

export interface LinkedInUpdate {
  section: string;
  content: string;
}

export async function startLinkedInUpdate(
  sessionId: string,
  updates: LinkedInUpdate[],
  linkedinUrl?: string
): Promise<{ status: string; message: string }> {
  const res = await authenticatedFetch(`${API_BASE}/api/sessions/${sessionId}/linkedin-update`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ updates, linkedin_url: linkedinUrl }),
  });
  if (!res.ok) throw new Error(`LinkedIn update failed: ${res.statusText}`);
  return res.json();
}

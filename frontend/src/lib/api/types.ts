// Copyright (c) 2026 V2 Software LLC. All rights reserved.

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
  verified_open?: boolean;
  verify_note?: string;
}

export interface ScoredJob {
  eligibility_status?: "met" | "not_met" | "unknown";
  eligibility_reasons?: string[];
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
  total_uncertain?: number;
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
  | "application_submitted"
  | "application_failed"
  | "application_start"
  | "application_browser_action"
  | "verification_progress"
  | "backfill_progress"
  | "reporting_progress"
  | "needs_intervention"
  | "ready_to_submit"
  | "login_required"
  | "login_complete"
  | "captcha_detected"
  | "browser_live_view"
  | "browser_live_view_ended"
  | "done"
  | "error"
  | "ping";

export interface SSEEvent {
  type: SSEEventType;
  data: Record<string, unknown>;
}

import type { ApplicationQuestion, EmployerApplication } from "@/components/ApplicationFollowups";
import type { CoachOutput } from "@/lib/api";

export type SessionData = {
  employer_application_queue?: Record<string, EmployerApplication>;
  application_questions?: Record<string, ApplicationQuestion>;
  session_summary?: boolean;
  session_id: string;
  status: string;
  pause_resume_node?: string | null;
  status_before_pause?: string | null;
  keywords: string[];
  locations?: string[];
  remote_only?: boolean;
  salary_min?: number | null;
  scored_jobs: Array<{
    job: {
      id: string;
      title: string;
      company: string;
      location: string;
      url: string;
      board: string;
    };
    score: number;
    breakdown: Record<string, number>;
  }>;
  applications_submitted: Array<{
    job_id?: string;
    job?: { id: string; title: string; company: string; url: string; board: string };
    status: string;
    submitted_at?: string;
  }>;
  applications_failed: Array<{
    job_id?: string;
    job?: { id: string; title: string; company: string; url: string; board: string };
    error_category?: string;
    error_message?: string;
    error?: string;
  }>;
  coach_output?: CoachOutput;
  coach_chat_history?: Array<{ role: string; text: string }>;
  linkedin_url?: string;
  applications_used: number;
  application_queue?: string[];
  applications_skipped: string[] | number;
  created_at?: string;
  session_config?: {
    discovery_mode?: string;
    job_urls?: string[];
    [key: string]: unknown;
  };
  job_urls?: string[];
};

export type SessionSummaryData = {
  session_id: string;
  total_discovered: number;
  total_scored: number;
  total_applied: number;
  total_failed: number;
  total_uncertain?: number;
  total_skipped: number;
  top_companies: string[];
  avg_fit_score: number;
  resume_score: { overall: number } | null;
  duration_minutes: number;
  next_steps: string[];
};

export type ScoredJobData = {
  eligibility_status?: "met" | "not_met" | "unknown";
  eligibility_reasons?: string[];
  job: {
    id: string;
    title: string;
    company: string;
    location: string;
    url: string;
    board: string;
  };
  score: number;
  score_breakdown?: Record<string, number>;
  reasons?: string[];
  fit_summary?: string;
};

export type SSEEvent = {
  employer_application_queue?: Record<string, EmployerApplication>;
  application_questions?: Record<string, ApplicationQuestion>;
  event: string;
  agent?: string;
  status?: string;
  message?: string;
  data?: Record<string, unknown>;
  timestamp?: string;
  jobs_found?: number;
  scored_count?: number;
  coach_output?: Record<string, unknown>;
  scored_jobs?: ScoredJobData[];
  agent_statuses?: Record<string, string>;
  keywords?: string[];
  locations?: string[];
  session_summary?: SessionSummaryData;
  step?: string;
  progress?: number;
  board?: string;
  count?: number;
  error?: boolean;
  submitted?: number;
  failed?: number;
  skipped?: number;
  current?: number;
  total?: number;
  section?: string;
  success?: boolean;
  results?: Array<{
    section: string;
    label: string;
    success: boolean;
    error?: string | null;
  }>;
};


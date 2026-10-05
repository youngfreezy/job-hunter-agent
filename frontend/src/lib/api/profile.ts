// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { API_BASE } from "./config";
import { authenticatedFetch } from "./transport";

export interface ResumeAnalysis {
  keywords: string[];
  locations: string[];
  experience_level: string | null;
  suggested_job_boards: string[];
  remote_likely: boolean;
}

export async function analyzeResume(resumeText: string): Promise<ResumeAnalysis> {
  const res = await authenticatedFetch(`${API_BASE}/api/resume/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resume_text: resumeText }),
  });
  if (!res.ok) throw new Error(`Failed to analyze resume: ${res.statusText}`);
  return res.json();
}

export async function parseResume(
  file: File
): Promise<{ text: string; filename: string; file_path?: string; resume_uuid?: string }> {
  const form = new FormData();
  form.append("file", file);
  const res = await authenticatedFetch(`${API_BASE}/api/sessions/parse-resume`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail || `Failed to parse resume: ${res.statusText}`);
  }
  return res.json();
}

export async function updateMinimumSubmitted(value: number): Promise<{ minimum_submitted_applications: number }> {
  const res = await authenticatedFetch(`${API_BASE}/api/auth/me/minimum-submitted`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ minimum_submitted_applications: value }),
  });
  if (!res.ok) throw new Error("Failed to update minimum submitted preference");
  return res.json();
}

export async function getApplicationRules(): Promise<string> {
  const res = await authenticatedFetch(`${API_BASE}/api/auth/me/application-rules`, {});
  if (!res.ok) throw new Error("Could not load your current rules. Your answer has not been saved.");
  const data = await res.json();
  if (typeof data.application_rules !== "string") throw new Error("Could not read your application rules. Your answer has not been saved.");
  return data.application_rules;
}

export async function updateApplicationRules(rules: string): Promise<{ application_rules: string }> {
  const res = await authenticatedFetch(`${API_BASE}/api/auth/me/application-rules`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ application_rules: rules }),
  });
  if (!res.ok) throw new Error("Failed to update application rules");
  return res.json();
}

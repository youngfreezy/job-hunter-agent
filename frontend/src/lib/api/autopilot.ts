// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { API_BASE } from "./config";
import { authenticatedFetch } from "./transport";

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
  is_running: boolean;
  created_at: string;
}

export async function listAutopilotSchedules(): Promise<AutopilotSchedule[]> {
  const res = await authenticatedFetch(`${API_BASE}/api/autopilot/schedules`, {});
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
  const res = await authenticatedFetch(`${API_BASE}/api/autopilot/schedules`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error("Failed to create autopilot schedule");
  return res.json();
}

export async function updateAutopilotSchedule(
  id: string,
  updates: Partial<AutopilotSchedule>
): Promise<AutopilotSchedule> {
  const res = await authenticatedFetch(`${API_BASE}/api/autopilot/schedules/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  if (!res.ok) throw new Error("Failed to update autopilot schedule");
  return res.json();
}

export async function deleteAutopilotSchedule(id: string): Promise<void> {
  const res = await authenticatedFetch(`${API_BASE}/api/autopilot/schedules/${id}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to delete autopilot schedule");
}

export async function toggleAutopilotPause(id: string): Promise<AutopilotSchedule> {
  const res = await authenticatedFetch(`${API_BASE}/api/autopilot/schedules/${id}/pause`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to toggle autopilot pause");
  return res.json();
}

export async function triggerAutopilotNow(id: string): Promise<{ triggered: boolean }> {
  const res = await authenticatedFetch(`${API_BASE}/api/autopilot/schedules/${id}/run-now`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to trigger autopilot run");
  return res.json();
}

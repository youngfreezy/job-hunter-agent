// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  AutopilotSchedule,
  listAutopilotSchedules,
  createAutopilotSchedule,
  deleteAutopilotSchedule,
  toggleAutopilotPause,
  triggerAutopilotNow,
} from "@/lib/api";

const CRON_PRESETS = [
  { label: "Weekdays at 8 AM", value: "0 8 * * 1-5" },
  { label: "Weekdays at 9 AM", value: "0 9 * * 1-5" },
  { label: "Daily at 8 AM", value: "0 8 * * *" },
  { label: "Monday at 9 AM", value: "0 9 * * 1" },
  { label: "Mon/Wed/Fri at 8 AM", value: "0 8 * * 1,3,5" },
];

function cronToLabel(cron: string): string {
  const preset = CRON_PRESETS.find((p) => p.value === cron);
  return preset?.label ?? cron;
}

function relativeTime(iso: string | null): string {
  if (!iso) return "Never";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function formatNextRun(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export default function AutopilotPage() {
  const [schedules, setSchedules] = useState<AutopilotSchedule[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);

  // Create form state
  const [name, setName] = useState("My Job Search");
  const [keywords, setKeywords] = useState("");
  const [locations, setLocations] = useState("Remote");
  const [cronExpression, setCronExpression] = useState("0 8 * * 1-5");
  const [autoApprove, setAutoApprove] = useState(false);
  const [creating, setCreating] = useState(false);

  async function load() {
    try {
      const data = await listAutopilotSchedules();
      setSchedules(data);
    } catch (err) {
      console.error("Failed to load schedules", err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleCreate() {
    if (!keywords.trim()) return;
    setCreating(true);
    try {
      await createAutopilotSchedule({
        name,
        keywords: keywords
          .split(",")
          .map((k) => k.trim())
          .filter(Boolean),
        locations: locations
          .split(",")
          .map((l) => l.trim())
          .filter(Boolean),
        cron_expression: cronExpression,
        auto_approve: autoApprove,
      });
      setShowCreate(false);
      setName("My Job Search");
      setKeywords("");
      setLocations("Remote");
      setCronExpression("0 8 * * 1-5");
      setAutoApprove(false);
      await load();
    } catch (err) {
      console.error("Failed to create schedule", err);
    } finally {
      setCreating(false);
    }
  }

  async function handleTogglePause(id: string) {
    try {
      await toggleAutopilotPause(id);
      await load();
    } catch (err) {
      console.error("Failed to toggle pause", err);
    }
  }

  async function handleRunNow(id: string) {
    try {
      await triggerAutopilotNow(id);
      await load();
    } catch (err) {
      console.error("Failed to trigger run", err);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Delete this autopilot schedule?")) return;
    try {
      await deleteAutopilotSchedule(id);
      await load();
    } catch (err) {
      console.error("Failed to delete schedule", err);
    }
  }

  if (loading) return null;

  return (
    <main className="mx-auto max-w-3xl px-4 py-10 space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Autopilot</h1>
        <p className="mt-1 text-muted-foreground">
          Set up recurring job searches that run automatically on a schedule.
        </p>
      </div>

      {/* Schedule list */}
      {schedules.length === 0 && !showCreate && (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-muted-foreground mb-4">
              No autopilot schedules yet. Create one to automate your job search.
            </p>
            <Button onClick={() => setShowCreate(true)}>Create Schedule</Button>
          </CardContent>
        </Card>
      )}

      {schedules.map((sched) => (
        <Card key={sched.id}>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-lg">{sched.name}</CardTitle>
              <div className="flex items-center gap-2">
                {sched.is_active ? (
                  <Badge variant="default">Active</Badge>
                ) : (
                  <Badge variant="secondary">Paused</Badge>
                )}
                {sched.auto_approve && <Badge variant="outline">Auto-approve</Badge>}
              </div>
            </div>
            <CardDescription>{cronToLabel(sched.cron_expression)}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-muted-foreground">Keywords:</span>{" "}
                <span className="font-medium">{sched.keywords.join(", ")}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Locations:</span>{" "}
                <span className="font-medium">{sched.locations.join(", ")}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Last run:</span>{" "}
                <span className="font-medium">{relativeTime(sched.last_run_at)}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Next run:</span>{" "}
                <span className="font-medium">
                  {sched.is_active ? formatNextRun(sched.next_run_at) : "—"}
                </span>
              </div>
            </div>
            {sched.last_session_id && (
              <div className="mt-3">
                <Link
                  href={`/session/${sched.last_session_id}`}
                  className="text-sm text-blue-600 hover:underline"
                >
                  View last session
                </Link>
              </div>
            )}
          </CardContent>
          <CardFooter className="gap-2">
            <Button size="sm" variant="outline" onClick={() => handleTogglePause(sched.id)}>
              {sched.is_active ? "Pause" : "Resume"}
            </Button>
            {sched.is_active && (
              <Button size="sm" variant="outline" onClick={() => handleRunNow(sched.id)}>
                Run Now
              </Button>
            )}
            <Button size="sm" variant="destructive" onClick={() => handleDelete(sched.id)}>
              Delete
            </Button>
          </CardFooter>
        </Card>
      ))}

      {/* Create form */}
      {showCreate && (
        <Card>
          <CardHeader>
            <CardTitle>New Autopilot Schedule</CardTitle>
            <CardDescription>
              Configure your recurring job search. The system will discover and score jobs, then
              email you for approval before applying.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full rounded-md border px-3 py-2 text-sm bg-background"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">
                Keywords <span className="text-muted-foreground">(comma-separated)</span>
              </label>
              <input
                type="text"
                value={keywords}
                onChange={(e) => setKeywords(e.target.value)}
                placeholder="software engineer, backend developer"
                className="w-full rounded-md border px-3 py-2 text-sm bg-background"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">
                Locations <span className="text-muted-foreground">(comma-separated)</span>
              </label>
              <input
                type="text"
                value={locations}
                onChange={(e) => setLocations(e.target.value)}
                placeholder="Remote, New York, NY"
                className="w-full rounded-md border px-3 py-2 text-sm bg-background"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Schedule</label>
              <select
                value={cronExpression}
                onChange={(e) => setCronExpression(e.target.value)}
                className="w-full rounded-md border px-3 py-2 text-sm bg-background"
              >
                {CRON_PRESETS.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="auto-approve"
                checked={autoApprove}
                onChange={(e) => setAutoApprove(e.target.checked)}
                className="rounded"
              />
              <label htmlFor="auto-approve" className="text-sm">
                Auto-approve applications (skip email approval step)
              </label>
            </div>
          </CardContent>
          <CardFooter className="gap-2">
            <Button onClick={handleCreate} disabled={creating || !keywords.trim()}>
              {creating ? "Creating..." : "Create Schedule"}
            </Button>
            <Button variant="outline" onClick={() => setShowCreate(false)}>
              Cancel
            </Button>
          </CardFooter>
        </Card>
      )}

      {/* Create button (when schedules exist) */}
      {schedules.length > 0 && !showCreate && (
        <Button onClick={() => setShowCreate(true)}>New Schedule</Button>
      )}
    </main>
  );
}

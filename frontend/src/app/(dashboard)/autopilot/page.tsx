// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
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
  updateAutopilotSchedule,
  deleteAutopilotSchedule,
  toggleAutopilotPause,
  triggerAutopilotNow,
  getAuthHeaders,
} from "@/lib/api";
import { toast } from "sonner";

const CRON_PRESETS = [
  { label: "Weekdays at 8 AM", value: "0 8 * * 1-5" },
  { label: "Weekdays at 9 AM", value: "0 9 * * 1-5" },
  { label: "Daily at 8 AM", value: "0 8 * * *" },
  { label: "Monday at 9 AM", value: "0 9 * * 1" },
  { label: "Mon/Wed/Fri at 8 AM", value: "0 8 * * 1,3,5" },
  { label: "Custom time...", value: "custom" },
];

/** Build a cron expression for a specific local hour/minute on selected days. */
function buildCustomCron(hour: number, minute: number, days: string): string {
  return `${minute} ${hour} * * ${days}`;
}

const DAY_OPTIONS = [
  { label: "Every day", value: "*" },
  { label: "Weekdays (Mon-Fri)", value: "1-5" },
  { label: "Mon/Wed/Fri", value: "1,3,5" },
  { label: "Tue/Thu", value: "2,4" },
  { label: "Monday only", value: "1" },
  { label: "Weekends", value: "0,6" },
];

function cronToLabel(cron: string): string {
  const preset = CRON_PRESETS.find((p) => p.value === cron);
  if (preset) return preset.label;

  // Parse custom cron into a readable string
  const parts = cron.split(" ");
  if (parts.length !== 5) return cron;
  const [minute, hour, , , dayOfWeek] = parts;
  const h = parseInt(hour);
  const m = parseInt(minute);
  const timeStr = `${h === 0 ? 12 : h > 12 ? h - 12 : h}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;

  const dayMap: Record<string, string> = {
    "*": "daily",
    "1-5": "weekdays",
    "1,3,5": "Mon/Wed/Fri",
    "2,4": "Tue/Thu",
    "1": "Mondays",
    "0,6": "weekends",
  };
  const dayStr = dayMap[dayOfWeek] ?? dayOfWeek;

  return `${dayStr.charAt(0).toUpperCase() + dayStr.slice(1)} at ${timeStr}`;
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
  const router = useRouter();
  const [schedules, setSchedules] = useState<AutopilotSchedule[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  // Create form state
  const [name, setName] = useState("My Job Search");
  const [keywords, setKeywords] = useState("");
  const [locations, setLocations] = useState("Remote");
  const [cronExpression, setCronExpression] = useState("0 8 * * 1-5");
  const [customHour, setCustomHour] = useState(() => String(new Date().getHours()).padStart(2, "0"));
  const [customMinute, setCustomMinute] = useState(() => String(new Date().getMinutes()).padStart(2, "0"));
  const [customDays, setCustomDays] = useState("1-5");
  const [autoApprove, setAutoApprove] = useState(false);
  const [creating, setCreating] = useState(false);

  // Edit form state
  const [editName, setEditName] = useState("");
  const [editKeywords, setEditKeywords] = useState("");
  const [editLocations, setEditLocations] = useState("");
  const [editCron, setEditCron] = useState("");
  const [editCustomHour, setEditCustomHour] = useState("08");
  const [editCustomMinute, setEditCustomMinute] = useState("00");
  const [editCustomDays, setEditCustomDays] = useState("1-5");
  const [editAutoApprove, setEditAutoApprove] = useState(false);
  const [saving, setSaving] = useState(false);

  function startEdit(sched: AutopilotSchedule) {
    setEditingId(sched.id);
    setEditName(sched.name);
    setEditKeywords(sched.keywords.join(", "));
    setEditLocations(sched.locations.join(", "));
    const isPreset = CRON_PRESETS.some((p) => p.value === sched.cron_expression);
    setEditCron(isPreset ? sched.cron_expression : "custom");
    if (!isPreset) {
      const parts = sched.cron_expression.split(" ");
      setEditCustomMinute((parts[0] ?? "0").padStart(2, "0"));
      setEditCustomHour((parts[1] ?? "8").padStart(2, "0"));
      setEditCustomDays(parts[4] ?? "1-5");
    }
    setEditAutoApprove(sched.auto_approve);
  }

  async function handleSaveEdit() {
    if (!editingId || !editKeywords.trim()) return;
    setSaving(true);
    try {
      const finalCron =
        editCron === "custom"
          ? buildCustomCron(parseInt(editCustomHour), parseInt(editCustomMinute), editCustomDays)
          : editCron;
      await updateAutopilotSchedule(editingId, {
        name: editName,
        keywords: editKeywords.split(",").map((k) => k.trim()).filter(Boolean),
        locations: editLocations.split(",").map((l) => l.trim()).filter(Boolean),
        cron_expression: finalCron,
        auto_approve: editAutoApprove,
      } as Partial<AutopilotSchedule>);
      setEditingId(null);
      await load();
      toast.success("Schedule updated");
    } catch (err) {
      console.error("Failed to update schedule", err);
      toast.error("Failed to update schedule");
    } finally {
      setSaving(false);
    }
  }

  async function load() {
    try {
      const headers = await getAuthHeaders();
      if (!headers.Authorization) {
        router.push("/login");
        return;
      }
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
      const finalCron =
        cronExpression === "custom"
          ? buildCustomCron(parseInt(customHour), parseInt(customMinute), customDays)
          : cronExpression;
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
        cron_expression: finalCron,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        auto_approve: autoApprove,
      });
      setShowCreate(false);
      setName("My Job Search");
      setKeywords("");
      setLocations("Remote");
      setCronExpression("0 8 * * 1-5");
      setAutoApprove(false);
      await load();
      toast.success("Schedule created");
    } catch (err) {
      console.error("Failed to create schedule", err);
      toast.error("Failed to create schedule");
    } finally {
      setCreating(false);
    }
  }

  async function handleTogglePause(id: string) {
    const schedule = schedules.find((s) => s.id === id);
    try {
      await toggleAutopilotPause(id);
      await load();
      toast.success(schedule?.is_active ? "Schedule paused" : "Schedule resumed");
    } catch (err) {
      console.error("Failed to toggle pause", err);
      toast.error("Failed to update schedule");
    }
  }

  async function handleRunNow(id: string) {
    try {
      await triggerAutopilotNow(id);
      await load();
      toast.success("Schedule triggered — check your dashboard");
    } catch (err) {
      console.error("Failed to trigger run", err);
      toast.error("Failed to trigger schedule");
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Delete this autopilot schedule?")) return;
    try {
      await deleteAutopilotSchedule(id);
      await load();
      toast.success("Schedule deleted");
    } catch (err) {
      console.error("Failed to delete schedule", err);
      toast.error("Failed to delete schedule");
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

      {[...schedules].sort((a, b) => {
        const rank = (s: typeof a) => (s.is_running ? 0 : s.is_active ? 1 : 2);
        return rank(a) - rank(b);
      }).map((sched) => (
        <Card key={sched.id}>
          {editingId === sched.id ? (
            <>
              <CardHeader>
                <CardTitle>Edit Schedule</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-1">Name</label>
                  <input
                    type="text"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    className="w-full rounded-md border px-3 py-2 text-sm bg-background"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">
                    Keywords <span className="text-muted-foreground">(comma-separated)</span>
                  </label>
                  <input
                    type="text"
                    value={editKeywords}
                    onChange={(e) => setEditKeywords(e.target.value)}
                    className="w-full rounded-md border px-3 py-2 text-sm bg-background"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">
                    Locations <span className="text-muted-foreground">(comma-separated)</span>
                  </label>
                  <input
                    type="text"
                    value={editLocations}
                    onChange={(e) => setEditLocations(e.target.value)}
                    className="w-full rounded-md border px-3 py-2 text-sm bg-background"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Schedule</label>
                  <select
                    value={editCron}
                    onChange={(e) => setEditCron(e.target.value)}
                    className="w-full rounded-md border px-3 py-2 text-sm bg-background"
                  >
                    {CRON_PRESETS.map((p) => (
                      <option key={p.value} value={p.value}>{p.label}</option>
                    ))}
                  </select>
                </div>
                {editCron === "custom" && (
                  <div className="space-y-3 rounded-md border p-3 bg-muted/30">
                    <div className="flex items-center gap-2">
                      <label className="text-sm font-medium w-12">Time</label>
                      <select
                        value={editCustomHour}
                        onChange={(e) => setEditCustomHour(e.target.value)}
                        className="rounded-md border px-2 py-1.5 text-sm bg-background"
                      >
                        {Array.from({ length: 24 }, (_, i) => (
                          <option key={i} value={String(i).padStart(2, "0")}>
                            {i === 0 ? "12 AM" : i < 12 ? `${i} AM` : i === 12 ? "12 PM" : `${i - 12} PM`}
                          </option>
                        ))}
                      </select>
                      <span className="text-muted-foreground">:</span>
                      <input
                        type="text"
                        inputMode="numeric"
                        maxLength={2}
                        placeholder="00"
                        value={editCustomMinute}
                        onChange={(e) => setEditCustomMinute(e.target.value.replace(/\D/g, "").slice(0, 2))}
                        onBlur={() => {
                          const n = Math.min(59, Math.max(0, Number(editCustomMinute) || 0));
                          setEditCustomMinute(String(n).padStart(2, "0"));
                        }}
                        className="rounded-md border px-2 py-1.5 text-sm bg-background w-14 text-center tabular-nums"
                      />
                      <span className="text-xs text-muted-foreground ml-1">(your local time)</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <label className="text-sm font-medium w-12">Days</label>
                      <select
                        value={editCustomDays}
                        onChange={(e) => setEditCustomDays(e.target.value)}
                        className="rounded-md border px-2 py-1.5 text-sm bg-background flex-1"
                      >
                        {DAY_OPTIONS.map((d) => (
                          <option key={d.value} value={d.value}>{d.label}</option>
                        ))}
                      </select>
                    </div>
                  </div>
                )}
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id={`edit-auto-approve-${sched.id}`}
                    checked={editAutoApprove}
                    onChange={(e) => setEditAutoApprove(e.target.checked)}
                    className="rounded"
                  />
                  <label htmlFor={`edit-auto-approve-${sched.id}`} className="text-sm">
                    Auto-approve applications (skip shortlist review step)
                  </label>
                </div>
              </CardContent>
              <CardFooter className="gap-2">
                <Button onClick={handleSaveEdit} disabled={saving || !editKeywords.trim()}>
                  {saving ? "Saving..." : "Save Changes"}
                </Button>
                <Button variant="outline" onClick={() => setEditingId(null)}>
                  Cancel
                </Button>
              </CardFooter>
            </>
          ) : (
            <>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-lg">{sched.name}</CardTitle>
                  <div className="flex items-center gap-2">
                    {sched.is_running ? (
                      <Badge className="bg-green-600 hover:bg-green-600 text-white animate-pulse">Running</Badge>
                    ) : sched.is_active ? (
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
                <Button size="sm" variant="outline" onClick={() => startEdit(sched)}>
                  Edit
                </Button>
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
            </>
          )}
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
            {cronExpression === "custom" && (
              <div className="space-y-3 rounded-md border p-3 bg-muted/30">
                <div className="flex items-center gap-2">
                  <label className="text-sm font-medium w-12">Time</label>
                  <select
                    value={customHour}
                    onChange={(e) => setCustomHour(e.target.value)}
                    className="rounded-md border px-2 py-1.5 text-sm bg-background"
                  >
                    {Array.from({ length: 24 }, (_, i) => (
                      <option key={i} value={String(i).padStart(2, "0")}>
                        {i === 0 ? "12 AM" : i < 12 ? `${i} AM` : i === 12 ? "12 PM" : `${i - 12} PM`}
                      </option>
                    ))}
                  </select>
                  <span className="text-muted-foreground">:</span>
                  <input
                    type="text"
                    inputMode="numeric"
                    maxLength={2}
                    placeholder="00"
                    value={customMinute}
                    onChange={(e) => {
                      const v = e.target.value.replace(/\D/g, "").slice(0, 2);
                      setCustomMinute(v);
                    }}
                    onBlur={() => {
                      const n = Math.min(59, Math.max(0, Number(customMinute) || 0));
                      setCustomMinute(String(n).padStart(2, "0"));
                    }}
                    className="rounded-md border px-2 py-1.5 text-sm bg-background w-14 text-center tabular-nums"
                  />
                  <span className="text-xs text-muted-foreground ml-1">(your local time)</span>
                </div>
                <div className="flex items-center gap-2">
                  <label className="text-sm font-medium w-12">Days</label>
                  <select
                    value={customDays}
                    onChange={(e) => setCustomDays(e.target.value)}
                    className="rounded-md border px-2 py-1.5 text-sm bg-background flex-1"
                  >
                    {DAY_OPTIONS.map((d) => (
                      <option key={d.value} value={d.value}>{d.label}</option>
                    ))}
                  </select>
                </div>
              </div>
            )}
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="auto-approve"
                checked={autoApprove}
                onChange={(e) => setAutoApprove(e.target.checked)}
                className="rounded"
              />
              <label htmlFor="auto-approve" className="text-sm">
                Auto-approve applications (skip shortlist review step)
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

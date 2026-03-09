// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { getWallet } from "@/lib/api";

const STORAGE_KEY = "jh_session_settings";

const JOB_BOARDS = [
  { id: "indeed", label: "Indeed" },
  { id: "linkedin", label: "LinkedIn" },
  { id: "glassdoor", label: "Glassdoor" },
  { id: "ziprecruiter", label: "ZipRecruiter" },
];

interface SessionSettings {
  ai_temperature: number;
  scoring_strictness: number;
  generate_cover_letters: boolean;
  job_boards: string[];
  max_jobs: number;
  application_mode: string;
}

const DEFAULT_SETTINGS: SessionSettings = {
  ai_temperature: 0.0,
  scoring_strictness: 0.5,
  generate_cover_letters: true,
  job_boards: ["indeed", "linkedin", "glassdoor", "ziprecruiter"],
  max_jobs: 20,
  application_mode: "auto_apply",
};

function loadSettings(): SessionSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
    }
  } catch {}
  return { ...DEFAULT_SETTINGS };
}

export default function SessionSettingsPage() {
  const [settings, setSettings] = useState<SessionSettings | null>(null);
  const [availableCredits, setAvailableCredits] = useState<number | null>(null);

  useEffect(() => {
    setSettings(loadSettings());
    getWallet()
      .then((w) => setAvailableCredits(w.free_remaining + Math.floor(w.balance)))
      .catch(() => {});
  }, []);

  if (!settings) return null;

  const save = (updated: SessionSettings) => {
    setSettings(updated);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
    toast.success("Settings saved");
  };

  const update = <K extends keyof SessionSettings>(
    key: K,
    value: SessionSettings[K]
  ) => {
    const updated = { ...settings, [key]: value };
    save(updated);
  };

  const toggleBoard = (boardId: string) => {
    const current = settings.job_boards;
    const updated = current.includes(boardId)
      ? current.filter((b) => b !== boardId)
      : [...current, boardId];
    if (updated.length === 0) return; // must have at least one
    update("job_boards", updated);
  };

  const handleReset = () => {
    save({ ...DEFAULT_SETTINGS });
  };

  return (
    <div className="container mx-auto max-w-2xl p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Session Settings</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Configure AI behavior and job search preferences. Settings apply to
            your next session.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={handleReset}>
          Reset Defaults
        </Button>
      </div>

      {/* AI Model Settings */}
      <Card>
        <CardContent className="p-6 space-y-5">
          <h2 className="text-lg font-semibold">AI Model Settings</h2>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium">Temperature</label>
              <span className="text-sm text-muted-foreground tabular-nums">
                {settings.ai_temperature.toFixed(1)}
              </span>
            </div>
            <input
              type="range"
              min="0"
              max="1"
              step="0.1"
              value={settings.ai_temperature}
              onChange={(e) =>
                update("ai_temperature", parseFloat(e.target.value))
              }
              className="w-full h-2 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
            />
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>Precise</span>
              <span>Creative</span>
            </div>
            <p className="text-xs text-muted-foreground">
              Lower = more predictable responses. Higher = more varied and
              creative.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Scoring */}
      <Card>
        <CardContent className="p-6 space-y-5">
          <h2 className="text-lg font-semibold">Scoring</h2>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium">Scoring Strictness</label>
              <span className="text-sm text-muted-foreground tabular-nums">
                {settings.scoring_strictness.toFixed(1)}
              </span>
            </div>
            <input
              type="range"
              min="0"
              max="1"
              step="0.1"
              value={settings.scoring_strictness}
              onChange={(e) =>
                update("scoring_strictness", parseFloat(e.target.value))
              }
              className="w-full h-2 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
            />
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>Lenient</span>
              <span>Strict</span>
            </div>
            <p className="text-xs text-muted-foreground">
              How selective the AI is when ranking job matches.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Application Behavior */}
      <Card>
        <CardContent className="p-6 space-y-5">
          <h2 className="text-lg font-semibold">Application Behavior</h2>

          {/* Cover letters toggle */}
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Generate Cover Letters</p>
              <p className="text-xs text-muted-foreground">
                Auto-generate a tailored cover letter for each application.
              </p>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={settings.generate_cover_letters}
              onClick={() =>
                update("generate_cover_letters", !settings.generate_cover_letters)
              }
              className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors ${
                settings.generate_cover_letters
                  ? "bg-primary"
                  : "bg-muted"
              }`}
            >
              <span
                className={`pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow-lg ring-0 transition-transform ${
                  settings.generate_cover_letters
                    ? "translate-x-5"
                    : "translate-x-0"
                }`}
              />
            </button>
          </div>

          {/* Job boards */}
          <div className="space-y-2">
            <p className="text-sm font-medium">Job Boards</p>
            <div className="flex flex-wrap gap-2">
              {JOB_BOARDS.map((board) => {
                const active = settings.job_boards.includes(board.id);
                return (
                  <button
                    key={board.id}
                    type="button"
                    onClick={() => toggleBoard(board.id)}
                    className={`px-3 py-1.5 text-sm rounded-md border transition-colors ${
                      active
                        ? "bg-primary text-primary-foreground border-primary"
                        : "bg-background text-muted-foreground border-border hover:bg-muted"
                    }`}
                  >
                    {board.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Max jobs slider */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium">Max Jobs</label>
              <span className="text-sm text-muted-foreground tabular-nums">
                {settings.max_jobs}
              </span>
            </div>
            <input
              type="range"
              min="5"
              max="50"
              step="5"
              value={settings.max_jobs}
              onChange={(e) =>
                update("max_jobs", parseInt(e.target.value, 10))
              }
              className="w-full h-2 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
            />
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>5</span>
              <span>50</span>
            </div>
            {availableCredits !== null &&
              settings.application_mode === "auto_apply" &&
              settings.max_jobs > availableCredits && (
                <div className="rounded-lg border border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30 px-4 py-3 text-sm">
                  <p className="font-medium text-amber-800 dark:text-amber-300">
                    You have {availableCredits} credit{availableCredits !== 1 ? "s" : ""} available
                  </p>
                  <p className="text-amber-700 dark:text-amber-400 text-xs mt-1">
                    With max jobs set to {settings.max_jobs}, some applications may be
                    skipped if you run out of credits.{" "}
                    <Link href="/billing" className="underline font-medium hover:text-amber-900 dark:hover:text-amber-200">
                      Buy Credits
                    </Link>
                  </p>
                </div>
              )}
          </div>
        </CardContent>
      </Card>

      {/* Application Mode */}
      <Card>
        <CardContent className="p-6 space-y-4">
          <h2 className="text-lg font-semibold">Application Mode</h2>

          <div className="space-y-3">
            <label className="flex items-start gap-3 cursor-pointer">
              <input
                type="radio"
                name="application_mode"
                value="auto_apply"
                checked={settings.application_mode === "auto_apply"}
                onChange={() => update("application_mode", "auto_apply")}
                className="mt-1 accent-primary"
              />
              <div>
                <p className="text-sm font-medium">Auto Apply</p>
                <p className="text-xs text-muted-foreground">
                  Automatically submit applications on your behalf.
                </p>
              </div>
            </label>

            <label className="flex items-start gap-3 cursor-pointer">
              <input
                type="radio"
                name="application_mode"
                value="materials_only"
                checked={settings.application_mode === "materials_only"}
                onChange={() => update("application_mode", "materials_only")}
                className="mt-1 accent-primary"
              />
              <div>
                <p className="text-sm font-medium">Materials Only</p>
                <p className="text-xs text-muted-foreground">
                  Generate tailored resumes and cover letters without
                  submitting applications.
                </p>
              </div>
            </label>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

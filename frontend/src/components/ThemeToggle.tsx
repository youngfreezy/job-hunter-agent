// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import {
  applyThemePreference,
  nextThemePreference,
  readThemePreference,
  THEME_CHANGE_EVENT,
  type ThemePreference,
} from "@/lib/theme";

const LABELS: Record<ThemePreference, string> = {
  system: "Theme: match system",
  light: "Theme: light",
  dark: "Theme: dark",
};

export function ThemeToggle({ className = "" }: { className?: string }) {
  // null until mounted so server and first client render match.
  const [pref, setPref] = useState<ThemePreference | null>(null);

  useEffect(() => {
    const sync = () => setPref(readThemePreference());
    sync();
    window.addEventListener(THEME_CHANGE_EVENT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(THEME_CHANGE_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  const current = pref ?? "system";
  const next = nextThemePreference(current);
  const Icon = current === "light" ? Sun : current === "dark" ? Moon : Monitor;

  return (
    <button
      type="button"
      onClick={() => {
        applyThemePreference(next);
        setPref(next);
      }}
      aria-label={`${LABELS[current]}. Switch to ${next === "system" ? "match system" : next}.`}
      title={LABELS[current]}
      data-umami-event="theme-toggle"
      className={`inline-flex h-8 w-8 items-center justify-center rounded-md text-zinc-600 transition-colors hover:bg-zinc-100 hover:text-zinc-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-white ${className}`}
    >
      <Icon className="h-4 w-4" aria-hidden="true" />
    </button>
  );
}

"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { modelSettings } from "@/lib/model-settings";
import { getBrowserbaseSettings } from "@/lib/api";
export function SetupNotice() {
  const [message, setMessage] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    Promise.all([modelSettings(),getBrowserbaseSettings()]).then(([model,browser]) => {
      const missing = [!model.ready && 'Anthropic API key', !browser.effective_configured && 'Browserbase API key and project', !(browser.effective_context_ids?.indeed || browser.context_ids.indeed) && 'saved Indeed login'].filter(Boolean);
      if (active) setMessage(missing.length ? `Before launching, set up: ${missing.join(', ')}.` : null);
    }).catch(() => { if (active) setMessage('Could not verify your API setup. Check Settings before launching.'); });
    return () => { active = false; };
  }, []);
  return message ? <div role="status" className="mb-6 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100">{message} <Link href="/settings" className="font-medium underline">Open Settings</Link></div> : null;
}

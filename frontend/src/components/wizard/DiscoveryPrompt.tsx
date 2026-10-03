"use client";

import { useField } from "formik";

const demoTargetSalary = Number(process.env.NEXT_PUBLIC_DEMO_TARGET_BASE_SALARY || 0);
const DEFAULT_DISCOVERY_PROMPT = "Find applied AI and AI-native software engineering positions in San Francisco that are hybrid or remote."
  + (demoTargetSalary > 0 ? ` Target base salary: $${demoTargetSalary.toLocaleString("en-US")}. Use my saved application rules for eligibility.` : "");

export function DiscoveryPrompt() {
  const [field, meta, helpers] = useField<string>("discoveryPrompt");
  return (
    <section className="rounded-xl border border-zinc-200 p-6 dark:border-zinc-800 space-y-3">
      <label htmlFor="discoveryPrompt" className="block text-lg font-semibold">Describe your job search</label>
      <textarea {...field} value={field.value || ""} id="discoveryPrompt" rows={4} maxLength={4000}
        placeholder={DEFAULT_DISCOVERY_PROMPT}
        aria-describedby="discoveryPromptHint"
        onKeyDown={(event) => {
          if (event.key === "Tab" && !event.shiftKey && !event.ctrlKey && !event.altKey && !event.metaKey && !field.value?.trim()) {
            event.preventDefault();
            helpers.setValue(DEFAULT_DISCOVERY_PROMPT);
          }
        }}
        className="w-full rounded-md border border-zinc-300 bg-transparent p-3 text-sm dark:border-zinc-700" />
      <p id="discoveryPromptHint" className="text-xs text-zinc-500">Press Tab in the empty box to use the example above.</p>
      <p className="text-sm text-zinc-500">Describe the roles, location, work arrangement, and exclusions you want. Your prompt guides discovery and ranking; you review the shortlist before applying.</p>
      <p className="text-sm text-zinc-500">For this demo, select Indeed only and connect your Indeed login in Settings → Browserbase.</p>
      {meta.touched && meta.error && <p role="alert" className="text-sm text-red-500">{meta.error}</p>}
    </section>
  );
}

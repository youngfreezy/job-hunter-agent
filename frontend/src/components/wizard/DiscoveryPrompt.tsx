"use client";

import { useField } from "formik";

export function DiscoveryPrompt() {
  const [field, meta] = useField<string>("discoveryPrompt");
  return (
    <section className="rounded-xl border border-zinc-200 p-6 dark:border-zinc-800 space-y-3">
      <label htmlFor="discoveryPrompt" className="block text-lg font-semibold">Describe your job search</label>
      <textarea {...field} value={field.value || ""} id="discoveryPrompt" rows={4} maxLength={4000}
        placeholder="Find applied AI and AI-native software engineering positions in San Francisco that are hybrid or remote."
        className="w-full rounded-md border border-zinc-300 bg-transparent p-3 text-sm dark:border-zinc-700" />
      <p className="text-sm text-zinc-500">Describe the roles, location, work arrangement, and exclusions you want. Your prompt guides discovery and ranking; you review the shortlist before applying.</p>
      <p className="text-sm text-zinc-500">For this demo, select Indeed only and connect your Indeed login in Settings → Browserbase.</p>
      {meta.touched && meta.error && <p role="alert" className="text-sm text-red-500">{meta.error}</p>}
    </section>
  );
}

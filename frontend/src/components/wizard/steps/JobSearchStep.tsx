// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useFormikContext } from "formik";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FormikKeywordInput } from "@/components/forms/FormikKeywordInput";
import { FormikInput } from "@/components/forms/FormikInput";
import { FormikCheckbox } from "@/components/forms/FormikCheckbox";

const RADIUS_OPTIONS = [10, 25, 50, 100, 150, 200];

export function JobSearchStep() {
  const { values, setFieldValue } = useFormikContext<{
    remoteOnly: boolean;
    searchRadius: number;
  }>();

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Search Keywords</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <FormikKeywordInput
            name="keywords"
            placeholder="e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner"
            helpText="Comma-separated. These are matched against job titles and descriptions."
          />
          <div className="rounded-xl bg-zinc-50 p-3 text-sm text-zinc-600 dark:bg-zinc-900/60 dark:text-zinc-400">
            <p className="font-medium text-zinc-900 dark:text-white">Why this matters</p>
            <p className="mt-1">
              Your keywords determine which jobs we find and how we tailor your resume. Be specific
              to get the best matches.
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Location & Preferences</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <FormikInput name="locations" placeholder="e.g. San Francisco, New York, Austin" />
          <p className="text-xs text-zinc-500">
            Comma-separated US cities. Currently available in the United States only.
          </p>
          <div className="flex items-center gap-4">
            <FormikCheckbox name="remoteOnly" label="Remote only" />
            <div className="flex items-center gap-2">
              <span className="text-sm text-zinc-600 dark:text-zinc-400">Min salary:</span>
              <FormikInput
                name="salaryMin"
                type="number"
                placeholder="e.g. 120000"
                className="w-32"
              />
            </div>
          </div>
          {!values.remoteOnly && (
            <div className="flex items-center gap-2">
              <span className="text-sm text-zinc-600 dark:text-zinc-400">Search radius:</span>
              <select
                value={values.searchRadius}
                onChange={(e) => setFieldValue("searchRadius", Number(e.target.value))}
                className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
              >
                {RADIUS_OPTIONS.map((r) => (
                  <option key={r} value={r}>
                    {r} miles
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="rounded-xl bg-zinc-50 p-3 text-sm text-zinc-600 dark:bg-zinc-900/60 dark:text-zinc-400">
            <p className="font-medium text-zinc-900 dark:text-white">Why this matters</p>
            <p className="mt-1">
              These preferences filter your results so you only see jobs that actually fit what
              you&apos;re looking for.
            </p>
          </div>
        </CardContent>
      </Card>
    </>
  );
}

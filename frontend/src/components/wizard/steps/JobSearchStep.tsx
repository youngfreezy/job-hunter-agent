"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FormikKeywordInput } from "@/components/forms/FormikKeywordInput";
import { FormikInput } from "@/components/forms/FormikInput";
import { FormikCheckbox } from "@/components/forms/FormikCheckbox";

export function JobSearchStep() {
  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Search Keywords</CardTitle>
        </CardHeader>
        <CardContent>
          <FormikKeywordInput
            name="keywords"
            placeholder="e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner"
            helpText="Comma-separated. These are matched against job titles and descriptions."
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Location & Preferences</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <FormikInput
            name="locations"
            placeholder="e.g. San Francisco, New York, Austin"
          />
          <p className="text-xs text-zinc-500">Comma-separated cities. Leave blank for any location.</p>
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
        </CardContent>
      </Card>
    </>
  );
}

"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FormikFileUpload } from "@/components/forms/FormikFileUpload";
import { FormikInput } from "@/components/forms/FormikInput";

export function ResumeProfileStep() {
  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Your Resume</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <FormikFileUpload />
          <p className="text-xs text-zinc-500">
            Upload your resume and our AI coach will analyze it, improve it, and create tailored versions for each job you apply to.
          </p>
          <div className="rounded-xl bg-zinc-50 p-3 text-sm text-zinc-600 dark:bg-zinc-900/60 dark:text-zinc-400">
            <p className="font-medium text-zinc-900 dark:text-white">
              Why this matters
            </p>
            <p className="mt-1">
              This becomes the foundation for every application. Our coach improves it first, then creates customized versions for each job.
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">LinkedIn Profile (Optional)</CardTitle>
        </CardHeader>
        <CardContent>
          <FormikInput
            name="linkedinUrl"
            placeholder="https://linkedin.com/in/yourprofile"
          />
          <p className="text-xs text-zinc-500 mt-2">
            If provided, we&apos;ll suggest improvements to keep your LinkedIn aligned with your resume.
          </p>
          <div className="mt-3 rounded-xl bg-zinc-50 p-3 text-sm text-zinc-600 dark:bg-zinc-900/60 dark:text-zinc-400">
            <p className="font-medium text-zinc-900 dark:text-white">
              Why this matters
            </p>
            <p className="mt-1">
              This is optional. Adding your LinkedIn helps us give better advice, but it won&apos;t slow down your job search.
            </p>
          </div>
        </CardContent>
      </Card>
    </>
  );
}

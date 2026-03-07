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
            Upload your resume and we&apos;ll extract the text automatically.
            The AI Career Coach will analyze, score, and rewrite it before
            applying.
          </p>
          <div className="rounded-xl bg-zinc-50 p-3 text-sm text-zinc-600 dark:bg-zinc-900/60 dark:text-zinc-400">
            <p className="font-medium text-zinc-900 dark:text-white">
              What this changes
            </p>
            <p className="mt-1">
              The coached resume becomes the base document for scoring,
              tailoring, and manual apply logs. Review the parsed text before
              launch if formatting matters.
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
            If provided, the Career Coach will advise on profile improvements.
          </p>
          <div className="mt-3 rounded-xl bg-zinc-50 p-3 text-sm text-zinc-600 dark:bg-zinc-900/60 dark:text-zinc-400">
            <p className="font-medium text-zinc-900 dark:text-white">
              What this changes
            </p>
            <p className="mt-1">
              LinkedIn guidance is optional. It improves profile consistency,
              but it does not block discovery or application flow.
            </p>
          </div>
        </CardContent>
      </Card>
    </>
  );
}

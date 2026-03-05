"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FormikFileUpload } from "@/components/forms/FormikFileUpload";
import { FormikTextarea } from "@/components/forms/FormikTextarea";
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

          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-zinc-200 dark:border-zinc-800" />
            </div>
            <div className="relative flex justify-center text-xs">
              <span className="bg-white dark:bg-zinc-950 px-2 text-zinc-500">or paste below</span>
            </div>
          </div>

          <FormikTextarea
            name="resumeText"
            placeholder="Paste your full resume text here..."
            rows={10}
          />
          <p className="text-xs text-zinc-500">
            The AI Career Coach will analyze, score, and rewrite your resume before applying.
            Your resume is encrypted at rest and auto-deleted after 30 days.
          </p>
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
        </CardContent>
      </Card>
    </>
  );
}

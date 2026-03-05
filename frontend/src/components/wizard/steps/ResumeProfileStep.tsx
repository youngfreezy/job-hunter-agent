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

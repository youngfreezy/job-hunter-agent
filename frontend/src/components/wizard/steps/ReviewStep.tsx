"use client";

import { useFormikContext } from "formik";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Pencil } from "lucide-react";
import type { SessionFormValues } from "@/lib/schemas/session";

interface ReviewStepProps {
  onEditStep: (step: number) => void;
}

export function ReviewStep({ onEditStep }: ReviewStepProps) {
  const { values } = useFormikContext<SessionFormValues>();

  const keywords = values.keywords.split(",").map((k) => k.trim()).filter(Boolean);
  const locations = values.locations.split(",").map((l) => l.trim()).filter(Boolean);

  return (
    <>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-lg">Job Search</CardTitle>
          <Button type="button" variant="ghost" size="sm" onClick={() => onEditStep(0)}>
            <Pencil className="w-4 h-4 mr-1" /> Edit
          </Button>
        </CardHeader>
        <CardContent className="space-y-3">
          <div>
            <p className="text-sm font-medium text-zinc-500">Keywords</p>
            <div className="flex flex-wrap gap-2 mt-1">
              {keywords.map((k) => <Badge key={k} variant="secondary">{k}</Badge>)}
            </div>
          </div>
          {locations.length > 0 && (
            <div>
              <p className="text-sm font-medium text-zinc-500">Locations</p>
              <p className="text-sm">{locations.join(", ")}</p>
            </div>
          )}
          <div className="flex gap-4 text-sm">
            {values.remoteOnly && <Badge variant="outline">Remote only</Badge>}
            {values.salaryMin && <span>Min salary: ${values.salaryMin}</span>}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-lg">Resume & Profile</CardTitle>
          <Button type="button" variant="ghost" size="sm" onClick={() => onEditStep(1)}>
            <Pencil className="w-4 h-4 mr-1" /> Edit
          </Button>
        </CardHeader>
        <CardContent className="space-y-3">
          <div>
            <p className="text-sm font-medium text-zinc-500">Resume</p>
            {values.resumeFileName ? (
              <p className="text-sm text-green-600">{values.resumeFileName}</p>
            ) : (
              <p className="text-sm text-zinc-600 dark:text-zinc-400 line-clamp-3">
                {values.resumeText.slice(0, 200)}{values.resumeText.length > 200 ? "..." : ""}
              </p>
            )}
          </div>
          {values.linkedinUrl && (
            <div>
              <p className="text-sm font-medium text-zinc-500">LinkedIn</p>
              <a href={values.linkedinUrl} className="text-sm text-blue-600 hover:underline" target="_blank" rel="noopener noreferrer">
                {values.linkedinUrl}
              </a>
            </div>
          )}
        </CardContent>
      </Card>
    </>
  );
}

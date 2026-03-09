// Copyright (c) 2026 V2 Software LLC. All rights reserved.

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

  const keywords = values.keywords
    .split(",")
    .map((k) => k.trim())
    .filter(Boolean);
  const locations = values.locations
    .split(",")
    .map((l) => l.trim())
    .filter(Boolean);

  return (
    <>
      <Card className="border-blue-200 bg-blue-50/60 dark:border-blue-900 dark:bg-blue-950/20">
        <CardHeader>
          <CardTitle className="text-lg">What Happens After You Start</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-3">
          <div className="rounded-xl bg-white/90 p-4 dark:bg-zinc-950/60">
            <p className="text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">First</p>
            <p className="mt-2 text-sm font-medium">Resume review</p>
            <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
              We&apos;ll pause so you can review and approve your improved resume.
            </p>
          </div>
          <div className="rounded-xl bg-white/90 p-4 dark:bg-zinc-950/60">
            <p className="text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">Next</p>
            <p className="mt-2 text-sm font-medium">Job shortlist review</p>
            <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
              You pick which matched jobs you want to apply to.
            </p>
          </div>
          <div className="rounded-xl bg-white/90 p-4 dark:bg-zinc-950/60">
            <p className="text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">
              During apply
            </p>
            <p className="mt-2 text-sm font-medium">You&apos;re always in control</p>
            <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
              Watch applications in real time, chat with the agent, or step in whenever you need to.
            </p>
          </div>
        </CardContent>
      </Card>

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
              {keywords.map((k) => (
                <Badge key={k} variant="secondary">
                  {k}
                </Badge>
              ))}
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
            {!values.remoteOnly && values.searchRadius !== 100 && (
              <Badge variant="outline">{values.searchRadius} mi radius</Badge>
            )}
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
              <div className="space-y-2">
                <p className="text-sm text-green-600">{values.resumeFileName}</p>
                <p className="text-xs text-zinc-500">Ready for coaching and tailoring.</p>
              </div>
            ) : (
              <p className="text-sm text-zinc-600 dark:text-zinc-400 line-clamp-3">
                {values.resumeText.slice(0, 200)}
                {values.resumeText.length > 200 ? "..." : ""}
              </p>
            )}
          </div>
          <div>
            <p className="text-sm font-medium text-zinc-500">Parse preview</p>
            <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400 line-clamp-4">
              {values.resumeText.slice(0, 280)}
              {values.resumeText.length > 280 ? "..." : ""}
            </p>
          </div>
          {values.linkedinUrl && (
            <div>
              <p className="text-sm font-medium text-zinc-500">LinkedIn</p>
              <a
                href={values.linkedinUrl}
                className="text-sm text-blue-600 hover:underline"
                target="_blank"
                rel="noopener noreferrer"
              >
                {values.linkedinUrl}
              </a>
            </div>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-lg">Configuration</CardTitle>
          <Button type="button" variant="ghost" size="sm" onClick={() => onEditStep(2)}>
            <Pencil className="w-4 h-4 mr-1" /> Edit
          </Button>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="font-medium text-zinc-500">Max jobs</p>
              <p>{values.maxJobs ?? 20}</p>
            </div>
            <div>
              <p className="font-medium text-zinc-500">Tailoring quality</p>
              <p className="capitalize">{values.tailoringQuality ?? "standard"}</p>
            </div>
            <div>
              <p className="font-medium text-zinc-500">Application mode</p>
              <p>{values.applicationMode === "materials_only" ? "Materials only" : "Auto apply"}</p>
            </div>
            <div>
              <p className="font-medium text-zinc-500">Cover letters</p>
              <p>{values.generateCoverLetters !== false ? "Yes" : "No"}</p>
            </div>
          </div>
          <div>
            <p className="text-sm font-medium text-zinc-500">Job boards</p>
            <div className="flex flex-wrap gap-2 mt-1">
              {(values.jobBoards ?? ["linkedin", "indeed", "glassdoor", "ziprecruiter"]).map(
                (b: string) => (
                  <Badge key={b} variant="secondary" className="capitalize">
                    {b}
                  </Badge>
                )
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    </>
  );
}

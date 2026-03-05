"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { CoachOutput } from "@/lib/api";
import { LinkedInUpdateButton, type LinkedInProgress } from "@/components/LinkedInUpdateButton";

const SCORE_FIELDS: Array<{ key: keyof CoachOutput["resume_score"]; label: string }> = [
  { key: "keyword_density", label: "Keyword Density" },
  { key: "impact_metrics", label: "Impact Metrics" },
  { key: "ats_compatibility", label: "ATS Compatibility" },
  { key: "readability", label: "Readability" },
  { key: "formatting", label: "Formatting" },
];

interface CoachPanelProps {
  coach: CoachOutput;
  sessionId?: string;
  linkedinUrl?: string;
  linkedinProgress?: LinkedInProgress | null;
  linkedinLoginRequired?: boolean;
}

export function CoachPanel({
  coach,
  sessionId,
  linkedinUrl,
  linkedinProgress,
  linkedinLoginRequired,
}: CoachPanelProps) {
  const scoreColor = (score: number) => {
    if (score >= 80) return "text-green-700 dark:text-green-400";
    if (score >= 60) return "text-yellow-700 dark:text-yellow-400";
    return "text-red-700 dark:text-red-400";
  };

  const scoreBadgeStyle = (score: number) => {
    if (score >= 80) return "bg-green-100 text-green-800 border-green-200 dark:bg-green-900/50 dark:text-green-300 dark:border-green-800";
    if (score >= 60) return "bg-yellow-100 text-yellow-800 border-yellow-200 dark:bg-yellow-900/50 dark:text-yellow-300 dark:border-yellow-800";
    return "bg-red-100 text-red-800 border-red-200 dark:bg-red-900/50 dark:text-red-300 dark:border-red-800";
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          Career Coach Results
          <Badge variant="outline" className={`font-semibold ${scoreBadgeStyle(coach.resume_score.overall)}`}>
            {coach.resume_score.overall}/100
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="score">
          <TabsList className="mb-3">
            <TabsTrigger value="score">Score</TabsTrigger>
            <TabsTrigger value="resume">Resume</TabsTrigger>
            <TabsTrigger value="cover">Cover Letter</TabsTrigger>
            <TabsTrigger value="linkedin">LinkedIn</TabsTrigger>
          </TabsList>

          <TabsContent value="score" className="space-y-3">
            <div className="bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded p-3 text-sm">
              {coach.confidence_message}
            </div>
            <div className="space-y-2">
              {SCORE_FIELDS.map(({ key, label }) => {
                const value = coach.resume_score[key];
                if (typeof value !== "number") return null;
                return (
                  <div key={key} className="flex items-center gap-3">
                    <span className="text-sm text-muted-foreground w-36">{label}</span>
                    <Progress value={value} className="flex-1" />
                    <span className={`text-sm font-medium w-10 text-right ${scoreColor(value)}`}>
                      {value}
                    </span>
                  </div>
                );
              })}
            </div>
            {coach.resume_score.feedback && coach.resume_score.feedback.length > 0 && (
              <div>
                <p className="text-sm font-medium mb-1">Improvement Suggestions</p>
                <ul className="space-y-1">
                  {coach.resume_score.feedback.map((fb, i) => (
                    <li key={i} className="text-sm text-muted-foreground flex items-start gap-2">
                      <span className="text-amber-500 mt-0.5">-</span>
                      {fb}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {coach.key_strengths && coach.key_strengths.length > 0 && (
              <div>
                <p className="text-sm font-medium mb-1.5">Key Strengths</p>
                <div className="flex flex-wrap gap-1.5">
                  {coach.key_strengths.map((s, i) => (
                    <Badge key={i} variant="secondary" className="text-xs">{s}</Badge>
                  ))}
                </div>
              </div>
            )}
            {coach.improvement_areas && coach.improvement_areas.length > 0 && (
              <div>
                <p className="text-sm font-medium mb-1.5">Areas for Growth</p>
                <ul className="space-y-2">
                  {coach.improvement_areas.map((a, i) => (
                    <li key={i} className="text-sm text-muted-foreground bg-muted/50 rounded-lg p-3 border border-border/50">
                      {a}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </TabsContent>

          <TabsContent value="resume">
            <pre className="text-sm whitespace-pre-wrap bg-muted/50 dark:bg-muted/30 rounded p-4 max-h-96 overflow-y-auto">
              {coach.rewritten_resume}
            </pre>
          </TabsContent>

          <TabsContent value="cover">
            <pre className="text-sm whitespace-pre-wrap bg-muted/50 dark:bg-muted/30 rounded p-4 max-h-96 overflow-y-auto">
              {coach.cover_letter_template}
            </pre>
          </TabsContent>

          <TabsContent value="linkedin" className="space-y-3">
            {coach.linkedin_advice.length === 0 ? (
              <p className="text-sm text-muted-foreground">No LinkedIn URL provided. Add your profile for personalized advice.</p>
            ) : (
              <>
                <ul className="space-y-2">
                  {coach.linkedin_advice.map((advice, i) => (
                    <li key={i} className="text-sm flex items-start gap-2">
                      <span className="text-blue-500 mt-0.5 shrink-0">-</span>
                      <span>{advice}</span>
                    </li>
                  ))}
                </ul>

                {sessionId && (
                  <div className="pt-3 border-t border-border/50">
                    <LinkedInUpdateButton
                      sessionId={sessionId}
                      linkedinAdvice={coach.linkedin_advice}
                      linkedinUrl={linkedinUrl}
                      linkedinProgress={linkedinProgress}
                      linkedinLoginRequired={linkedinLoginRequired}
                    />
                  </div>
                )}
              </>
            )}
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}

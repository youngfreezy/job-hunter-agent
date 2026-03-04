"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

interface ResumeScore {
  overall: number;
  breakdown: Record<string, number>;
}

interface CoachOutput {
  rewritten_resume: string;
  resume_score: ResumeScore;
  cover_letter_template: string;
  linkedin_advice: string[];
  confidence_message: string;
  key_strengths?: string[];
  improvement_areas?: string[];
}

export function CoachPanel({ coach }: { coach: CoachOutput }) {
  const scoreColor = (score: number) => {
    if (score >= 80) return "text-green-600";
    if (score >= 60) return "text-yellow-600";
    return "text-red-600";
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          Career Coach Results
          <Badge className={scoreColor(coach.resume_score.overall)}>
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
            {/* Confidence message */}
            <div className="bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded p-3 text-sm">
              {coach.confidence_message}
            </div>

            {/* Score breakdown */}
            <div className="space-y-2">
              {Object.entries(coach.resume_score.breakdown).map(([key, value]) => (
                <div key={key} className="flex items-center gap-3">
                  <span className="text-sm text-zinc-600 w-36 capitalize">
                    {key.replace(/_/g, " ")}
                  </span>
                  <Progress value={value} className="flex-1" />
                  <span className={`text-sm font-medium w-10 text-right ${scoreColor(value)}`}>
                    {value}
                  </span>
                </div>
              ))}
            </div>

            {/* Strengths */}
            {coach.key_strengths && coach.key_strengths.length > 0 && (
              <div>
                <p className="text-sm font-medium mb-1">Key Strengths</p>
                <div className="flex flex-wrap gap-1">
                  {coach.key_strengths.map((s, i) => (
                    <Badge key={i} variant="secondary" className="text-xs">{s}</Badge>
                  ))}
                </div>
              </div>
            )}
          </TabsContent>

          <TabsContent value="resume">
            <pre className="text-sm whitespace-pre-wrap bg-zinc-50 dark:bg-zinc-900 rounded p-4 max-h-96 overflow-y-auto">
              {coach.rewritten_resume}
            </pre>
          </TabsContent>

          <TabsContent value="cover">
            <pre className="text-sm whitespace-pre-wrap bg-zinc-50 dark:bg-zinc-900 rounded p-4 max-h-96 overflow-y-auto">
              {coach.cover_letter_template}
            </pre>
          </TabsContent>

          <TabsContent value="linkedin" className="space-y-2">
            {coach.linkedin_advice.length === 0 ? (
              <p className="text-sm text-zinc-500">No LinkedIn URL provided. Add your profile for personalized advice.</p>
            ) : (
              <ul className="space-y-2">
                {coach.linkedin_advice.map((advice, i) => (
                  <li key={i} className="text-sm flex items-start gap-2">
                    <span className="text-blue-500 mt-0.5">-</span>
                    {advice}
                  </li>
                ))}
              </ul>
            )}
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}

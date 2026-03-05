"use client";

import { useState, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import type { CoachOutput, LinkedInUpdate } from "@/lib/api";
import { startLinkedInUpdate, confirmLinkedInLogin } from "@/lib/api";

const SCORE_FIELDS: Array<{ key: keyof CoachOutput["resume_score"]; label: string }> = [
  { key: "keyword_density", label: "Keyword Density" },
  { key: "impact_metrics", label: "Impact Metrics" },
  { key: "ats_compatibility", label: "ATS Compatibility" },
  { key: "readability", label: "Readability" },
  { key: "formatting", label: "Formatting" },
];

function parseAdviceToUpdates(advice: string[]): LinkedInUpdate[] {
  const sectionKeywords: Record<string, string[]> = {
    headline: ["headline"],
    about: ["about section", "about "],
    featured: ["featured section", "featured"],
    skills: ["skills section", "skills"],
    experience: ["work history", "experience entry", "experience entries", "work experience"],
    education: ["education", "columbia", "university"],
    url: ["custom url", "linkedin url", "linkedin.com/in/"],
  };

  return advice.map((text) => {
    const lower = text.toLowerCase();
    let section = "general";
    for (const [key, keywords] of Object.entries(sectionKeywords)) {
      if (keywords.some((kw) => lower.includes(kw))) {
        section = key;
        break;
      }
    }
    return { section, content: text };
  });
}

const SECTION_LABELS: Record<string, string> = {
  headline: "Headline",
  about: "About / Summary",
  featured: "Featured Section",
  skills: "Skills",
  experience: "Work Experience",
  education: "Education",
  url: "Custom URL",
  general: "General Advice",
};

type ModalStep = "review" | "login" | "updating" | "done";

export interface LinkedInProgress {
  step: string;
  section: string;
  progress: number;
  success?: boolean;
  results?: Array<{ section: string; label: string; success: boolean; error?: string | null }>;
}

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

  // Modal + stepper state
  const [modalOpen, setModalOpen] = useState(false);
  const [modalStep, setModalStep] = useState<ModalStep>("review");
  const [proposedUpdates, setProposedUpdates] = useState<Array<LinkedInUpdate & { enabled: boolean }>>([]);
  const [loginConfirming, setLoginConfirming] = useState(false);
  const [startingUpdate, setStartingUpdate] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Transition to login step when SSE says login is required
  if (linkedinLoginRequired && modalStep === "review" && modalOpen && startingUpdate) {
    setModalStep("login");
    setStartingUpdate(false);
  }

  // Transition to updating step when progress starts flowing
  if (linkedinProgress && linkedinProgress.progress > 5 && modalStep === "login") {
    setModalStep("updating");
  }

  // Transition to done
  if (linkedinProgress && linkedinProgress.progress === 100 && modalStep === "updating") {
    setModalStep("done");
  }

  const handleOpenModal = useCallback(() => {
    const updates = parseAdviceToUpdates(coach.linkedin_advice);
    setProposedUpdates(updates.map((u) => ({ ...u, enabled: true })));
    setModalStep("review");
    setError(null);
    setModalOpen(true);
  }, [coach.linkedin_advice]);

  const handleConfirmAndStart = useCallback(async () => {
    if (!sessionId) return;

    const enabledUpdates = proposedUpdates.filter((u) => u.enabled);
    if (enabledUpdates.length === 0) {
      setError("Select at least one update to apply.");
      return;
    }

    setError(null);
    setStartingUpdate(true);

    try {
      await startLinkedInUpdate(
        sessionId,
        enabledUpdates.map(({ section, content }) => ({ section, content })),
        linkedinUrl,
      );
      // Modal stays open — will transition to "login" step when SSE event arrives
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start update");
      setStartingUpdate(false);
    }
  }, [sessionId, proposedUpdates, linkedinUrl]);

  const handleLoginConfirmed = useCallback(async () => {
    if (!sessionId) return;
    setLoginConfirming(true);
    setError(null);
    try {
      await confirmLinkedInLogin(sessionId);
      // Will transition to "updating" when progress SSE events arrive
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to confirm login");
    } finally {
      setLoginConfirming(false);
    }
  }, [sessionId]);

  const toggleUpdate = (index: number) => {
    setProposedUpdates((prev) =>
      prev.map((u, i) => (i === index ? { ...u, enabled: !u.enabled } : u))
    );
  };

  const stepperSteps = [
    { key: "review", label: "Review" },
    { key: "login", label: "Log In" },
    { key: "updating", label: "Updating" },
    { key: "done", label: "Done" },
  ];
  const currentStepIdx = stepperSteps.findIndex((s) => s.key === modalStep);

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
                    <Button onClick={handleOpenModal} className="w-full">
                      <svg className="w-4 h-4 mr-2" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
                      </svg>
                      Update My LinkedIn Profile
                    </Button>
                  </div>
                )}
              </>
            )}
          </TabsContent>
        </Tabs>
      </CardContent>

      {/* LinkedIn Update Dialog — multi-step flow */}
      <Dialog open={modalOpen} onOpenChange={(open) => {
        // Only allow closing during review step or when done
        if (!open && (modalStep === "review" || modalStep === "done")) {
          setModalOpen(false);
        }
      }}>
        <DialogContent className="max-w-2xl max-h-[85vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>Update LinkedIn Profile</DialogTitle>
            <DialogDescription className="sr-only">
              Follow the steps to update your LinkedIn profile with the recommended changes.
            </DialogDescription>
          </DialogHeader>

          {/* Stepper */}
          <div className="flex items-center gap-1 py-3 border-b border-border/50">
            {stepperSteps.map((s, i) => (
              <div key={s.key} className="flex items-center flex-1 last:flex-none">
                <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-all ${
                  i < currentStepIdx
                    ? "bg-blue-50 text-blue-700 dark:bg-blue-900/60 dark:text-blue-300"
                    : i === currentStepIdx
                    ? "bg-gradient-to-r from-blue-500 to-blue-600 text-white shadow-sm"
                    : "text-muted-foreground/60"
                }`}>
                  {i < currentStepIdx ? (
                    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  ) : i === currentStepIdx ? (
                    <span className="w-1.5 h-1.5 rounded-full bg-white" />
                  ) : (
                    <span className="w-1.5 h-1.5 rounded-full bg-current opacity-30" />
                  )}
                  {s.label}
                </div>
                {i < stepperSteps.length - 1 && (
                  <div className="flex-1 mx-1">
                    <div className={`h-0.5 rounded-full ${i < currentStepIdx ? "bg-blue-400" : "bg-border/50"}`} />
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Step Content */}
          <div className="flex-1 overflow-y-auto py-3 min-h-0">

            {/* Step 1: Review Changes */}
            {modalStep === "review" && (
              <div className="space-y-3">
                <p className="text-sm text-muted-foreground">
                  Select which updates to apply. A browser will open to LinkedIn where you&apos;ll log in first.
                </p>
                {proposedUpdates.map((update, i) => (
                  <label
                    key={i}
                    className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                      update.enabled
                        ? "bg-blue-50/50 dark:bg-blue-950/30 border-blue-200 dark:border-blue-800"
                        : "bg-muted/30 border-border/50 opacity-60"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={update.enabled}
                      onChange={() => toggleUpdate(i)}
                      className="mt-1 shrink-0 accent-blue-600"
                    />
                    <div className="min-w-0">
                      <p className="text-xs font-semibold text-blue-700 dark:text-blue-300 mb-0.5">
                        {SECTION_LABELS[update.section] || update.section}
                      </p>
                      <p className="text-sm text-foreground/80 leading-relaxed">
                        {update.content.length > 400 ? update.content.slice(0, 400) + "..." : update.content}
                      </p>
                    </div>
                  </label>
                ))}
                {error && <p className="text-sm text-red-600">{error}</p>}
                <div className="flex justify-end gap-2 pt-2">
                  <Button variant="outline" onClick={() => setModalOpen(false)}>Cancel</Button>
                  <Button onClick={handleConfirmAndStart} loading={startingUpdate}>
                    Open LinkedIn &amp; Continue
                  </Button>
                </div>
              </div>
            )}

            {/* Step 2: Login */}
            {modalStep === "login" && (
              <div className="flex flex-col items-center justify-center py-8 space-y-6">
                <div className="w-16 h-16 rounded-full bg-blue-100 dark:bg-blue-900/50 flex items-center justify-center">
                  <svg className="w-8 h-8 text-blue-600 dark:text-blue-400" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
                  </svg>
                </div>
                <div className="text-center space-y-2">
                  <h3 className="text-lg font-semibold">Log in to LinkedIn</h3>
                  <p className="text-sm text-muted-foreground max-w-sm">
                    A browser window has opened to LinkedIn. Log in to your account there, then come back and click the button below.
                  </p>
                </div>
                {error && <p className="text-sm text-red-600">{error}</p>}
                <Button
                  size="lg"
                  onClick={handleLoginConfirmed}
                  loading={loginConfirming}
                  className="px-8"
                >
                  I&apos;m Logged In — Start Updates
                </Button>
              </div>
            )}

            {/* Step 3: Updating */}
            {modalStep === "updating" && (
              <div className="space-y-4 py-4">
                <div className="text-center space-y-1">
                  <h3 className="text-base font-semibold">Updating your profile...</h3>
                  <p className="text-sm text-muted-foreground">
                    Watch the browser window — changes are being applied one at a time.
                  </p>
                </div>

                {linkedinProgress && (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-medium">{linkedinProgress.step}</p>
                      <span className="text-xs font-mono text-muted-foreground tabular-nums">{linkedinProgress.progress}%</span>
                    </div>
                    <Progress value={linkedinProgress.progress} className="h-2" />
                  </div>
                )}

                {/* Per-section status list */}
                {proposedUpdates.filter(u => u.enabled).map((update, i) => {
                  const isActive = linkedinProgress?.section === update.section;
                  const result = linkedinProgress?.results?.find(r => r.section === update.section);
                  return (
                    <div
                      key={i}
                      className={`flex items-center gap-3 px-3 py-2 rounded-lg border text-sm transition-colors ${
                        result?.success
                          ? "bg-green-50/50 dark:bg-green-950/30 border-green-200 dark:border-green-800"
                          : result && !result.success
                          ? "bg-red-50/50 dark:bg-red-950/30 border-red-200 dark:border-red-800"
                          : isActive
                          ? "bg-blue-50/50 dark:bg-blue-950/30 border-blue-200 dark:border-blue-800"
                          : "border-border/30"
                      }`}
                    >
                      {result?.success ? (
                        <svg className="w-4 h-4 text-green-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                      ) : result && !result.success ? (
                        <svg className="w-4 h-4 text-red-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      ) : isActive ? (
                        <span className="relative flex h-3 w-3 shrink-0">
                          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
                          <span className="relative inline-flex rounded-full h-3 w-3 bg-blue-500" />
                        </span>
                      ) : (
                        <span className="w-4 h-4 rounded-full border-2 border-border/50 shrink-0" />
                      )}
                      <span className={isActive ? "font-medium" : "text-muted-foreground"}>
                        {SECTION_LABELS[update.section] || update.section}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Step 4: Done */}
            {modalStep === "done" && (
              <div className="flex flex-col items-center justify-center py-8 space-y-6">
                <div className="w-16 h-16 rounded-full bg-green-100 dark:bg-green-900/50 flex items-center justify-center">
                  <svg className="w-8 h-8 text-green-600 dark:text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <div className="text-center space-y-2">
                  <h3 className="text-lg font-semibold">Profile Updated!</h3>
                  <p className="text-sm text-muted-foreground">
                    {linkedinProgress?.step || "Your LinkedIn profile has been updated."}
                  </p>
                </div>

                {/* Results summary */}
                {linkedinProgress?.results && (
                  <div className="w-full space-y-1.5">
                    {linkedinProgress.results.map((r, i) => (
                      <div key={i} className="flex items-center gap-2 text-sm px-3 py-1.5">
                        {r.success ? (
                          <svg className="w-4 h-4 text-green-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                          </svg>
                        ) : (
                          <svg className="w-4 h-4 text-red-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        )}
                        <span className={r.success ? "" : "text-red-600 dark:text-red-400"}>
                          {r.label}
                        </span>
                      </div>
                    ))}
                  </div>
                )}

                <Button onClick={() => { setModalOpen(false); setModalStep("review"); }}>
                  Close
                </Button>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { RecoveryNotice } from "@/components/RecoveryNotice";
import { ResumeUpload } from "@/components/ResumeUpload";
import { Button } from "@/components/ui/button";
import { API_BASE, apiFetch, createAuthenticatedStream, getAuthHeaders, getWallet, type SSEConnection } from "@/lib/api";
import { resultStreamError } from "@/lib/result-stream";
import type {
  PivotRole,
  RiskAssessment,
  SkillBridge
} from "@/lib/types/career-pivot";
import { riskColor, riskLabel } from "@/lib/utils";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { CareerPivotPaywall } from "@/components/career-pivot/CareerPivotPaywall";

import { CareerRiskReport } from "@/components/career-pivot/CareerRiskReport";

import { CareerPivotRecommendations } from "@/components/career-pivot/CareerPivotRecommendations";

export default function SessionCareerPivotPage() {
  useParams<{ id: string }>();
  const router = useRouter();
  const [pivotId, setPivotId] = useState<string | null>(null);
  const [status, setStatus] = useState("idle");
  const [, setStatusMessage] = useState("");
  const [risk, setRisk] = useState<RiskAssessment | null>(null);
  const [pivots, setPivots] = useState<PivotRole[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [streamAttempt, setStreamAttempt] = useState(0);
  const [expandedRadar, setExpandedRadar] = useState<number | null>(null);
  const [skillBridges, setSkillBridges] = useState<SkillBridge[]>([]);
  const [paywall, setPaywall] = useState<{
    count: number;
    message: string;
    cost: number;
  } | null>(null);
  const [unlocking, setUnlocking] = useState(false);
  const [walletBalance, setWalletBalance] = useState<number | null>(null);
  const [starting, setStarting] = useState(false);
  const [resumeText, setResumeText] = useState("");
  const hasResume = Boolean(resumeText.trim());

  // Start pivot session
  async function handleStart() {
    if(!resumeText.trim()) {
      setError("Please upload your resume first.");
      return;
    }
    setStarting(true);
    setError(null);
    try {
      const headers = await getAuthHeaders();
      const res = await apiFetch(`${API_BASE}/api/career-pivot`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({ resume_text: resumeText, location: "Remote" }),
      });
      if(!res.ok) throw new Error(`Failed: ${res.statusText}`);
      const { session_id } = await res.json();
      setPivotId(session_id);
      setStatus("connecting");
    } catch(err: unknown) {
      setError(err instanceof Error ? err.message : "An unknown error occurred");
      setStarting(false);
    }
  }

  // SSE connection
  useEffect(() => {
    if(!pivotId) return;
    let es: SSEConnection | null = null;
    es = createAuthenticatedStream(`${API_BASE}/api/career-pivot/${pivotId}/stream`);

    es.addEventListener("status", (e) => {
      const data = JSON.parse(e.data);
      setStatus(data.status);
      setStatusMessage(data.message);
    });

    es.addEventListener("risk_assessment", (e) => {
      setRisk(JSON.parse(e.data));
    });

    es.addEventListener("pivot_roles", (e) => {
      const data = JSON.parse(e.data);
      setPivots(data.recommended_pivots || []);
      setPaywall(null);
    });

    es.addEventListener("transferable_skills", (e) => {
      const data = JSON.parse(e.data);
      setSkillBridges(data.skill_bridges || []);
    });

    es.addEventListener("paywall", (e) => {
      const data = JSON.parse(e.data);
      setPaywall({ count: data.count, message: data.message, cost: data.cost });
      getWallet()
        .then((w) => setWalletBalance(w.balance))
        .catch(() => { });
    });

    es.addEventListener("done", () => {
      setStatus("completed");
      setStatusMessage("Analysis complete!");
      es?.close();
    });

    es.addEventListener("error", (event) => {
      setError(resultStreamError(event));
      es?.close();
    });

    return () => {
      es?.close();
    };
  }, [pivotId, streamAttempt]);

  async function handleUnlock() {
    if(!pivotId) return;
    setUnlocking(true);
    try {
      const auth = await getAuthHeaders();
      const res = await apiFetch(`${API_BASE}/api/career-pivot/${pivotId}/unlock`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...auth },
      });
      if(res.status === 402) {
        router.push("/billing");
        return;
      }
      if(!res.ok) throw new Error("Unlock failed");
    } catch(e) {
      setError(e instanceof Error ? e.message : "Failed to unlock");
    } finally {
      setUnlocking(false);
    }
  }

  // Single loading gate — show form or loading skeleton until pivots/paywall arrive
  const isLoading = pivots.length === 0 && !paywall && status !== "completed" && !error;

  if(isLoading && !starting) {
    return (
      <div className="container mx-auto max-w-4xl p-6 space-y-6">
        <h1 className="text-2xl font-bold">Career Change Advisor</h1>
        <p className="text-muted-foreground">
          Is your job safe from AI? Find out in 60 seconds — free.
        </p>
        <div className="bg-card border rounded-lg p-8 space-y-6">
          <div className="text-center space-y-3">
            <h2 className="text-xl font-semibold">Analyze your AI automation risk</h2>
            <p className="text-muted-foreground max-w-lg mx-auto">
              We&apos;ll analyze your resume against U.S. Department of Labor data to find your
              automation risk score, adjacent roles you&apos;re qualified for, and a learning plan
              to close skill gaps.
            </p>
          </div>

          <div className="max-w-lg mx-auto">
            <ResumeUpload onResumeReady={setResumeText} />
          </div>

          {error && <p className="text-destructive text-sm text-center">{error}</p>}

          <div className="text-center">
            <Button size="lg" onClick={handleStart} disabled={!hasResume} loading={starting}>
              Start Free Assessment
            </Button>
          </div>

          <p className="text-xs text-muted-foreground text-center">
            Powered by U.S. Department of Labor data. No credit card required.
          </p>
        </div>
      </div>
    );
  }

  if(isLoading && starting) {
    const statusText =
      status === "parsing_skills"
        ? "Parsing your resume..."
        : status === "researching_onet"
          ? "Researching your occupation..."
          : status === "assessing_risk"
            ? "Calculating your automation risk..."
            : status === "mapping_roles"
              ? "Finding adjacent roles you're qualified for..."
              : status === "mapping_cross_industry"
                ? "Mapping your skills to unexpected industries..."
                : "Starting your career analysis...";

    const progressWidth =
      status === "parsing_skills"
        ? "20%"
        : status === "researching_onet"
          ? "35%"
          : status === "assessing_risk"
            ? "50%"
            : status === "mapping_roles"
              ? "70%"
              : status === "mapping_cross_industry"
                ? "85%"
                : "10%";

    return (
      <div className="container mx-auto max-w-4xl p-6 space-y-6">
        <h1 className="text-2xl font-bold">Career Change Advisor</h1>
        <p className="text-muted-foreground">
          Is your job safe from AI? Find out in 60 seconds — free.
        </p>

        <div className="space-y-6 animate-in fade-in duration-300">
          {/* Progress bar */}
          <div className="bg-card border rounded-lg p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="animate-spin h-5 w-5 border-2 border-primary border-t-transparent rounded-full" />
              <p className="text-sm text-muted-foreground">{statusText}</p>
            </div>
            <div className="w-full bg-muted rounded-full h-1.5">
              <div
                className="bg-primary h-1.5 rounded-full animate-pulse transition-all duration-500"
                style={{ width: progressWidth }}
              />
            </div>
          </div>

          {/* Risk score — real data or skeleton */}
          {risk ? (
            <div className="bg-card border rounded-lg p-8 space-y-4">
              <div className="text-center space-y-3">
                <h2 className="text-lg font-medium text-muted-foreground">
                  Your AI Automation Risk
                </h2>
                <div className={`text-6xl font-bold ${riskColor(risk.automation_risk_score)}`}>
                  {Math.round(risk.automation_risk_score)}%
                </div>
                <p className={`text-sm font-semibold ${riskColor(risk.automation_risk_score)}`}>
                  {riskLabel(risk.automation_risk_score)}
                </p>
              </div>
              <div className="bg-muted/50 rounded-lg p-4 space-y-2">
                <div className="text-sm">
                  <span className="font-medium">{risk.parsed_role}</span>
                </div>
                <div className="flex gap-4 text-xs text-muted-foreground">
                  <span>{risk.years_experience} years experience</span>
                  <span>{risk.industry}</span>
                </div>
              </div>
            </div>
          ) : (
            <div className="bg-card border rounded-lg p-8 space-y-4">
              <div className="flex flex-col items-center space-y-3">
                <div className="h-4 w-40 bg-muted animate-pulse rounded" />
                <div className="h-14 w-20 bg-muted animate-pulse rounded" />
                <div className="h-3 w-24 bg-muted animate-pulse rounded" />
              </div>
              <div className="bg-muted/50 rounded-lg p-4 space-y-2">
                <div className="h-4 w-48 bg-muted animate-pulse rounded" />
                <div className="h-3 w-32 bg-muted animate-pulse rounded" />
              </div>
            </div>
          )}

          {/* Career comparison skeleton */}
          <div className="bg-card border rounded-lg p-6 space-y-3">
            <div className="h-5 w-40 bg-muted animate-pulse rounded" />
            <div className="h-3 w-64 bg-muted animate-pulse rounded" />
            <div className="h-[200px] flex items-end gap-3 pt-4">
              {[1, 2, 3].map((i) => (
                <div key={i} className="flex-1 flex flex-col items-center gap-2">
                  <div
                    className="w-full rounded-t bg-muted animate-pulse"
                    style={{ height: `${80 + i * 30}px` }}
                  />
                  <div className="h-3 w-16 bg-muted animate-pulse rounded" />
                </div>
              ))}
            </div>
          </div>

          {/* Role card skeletons */}
          {[1, 2].map((i) => (
            <div key={i} className="bg-card border rounded-lg p-6 space-y-3">
              <div className="flex items-center justify-between">
                <div className="h-5 w-48 bg-muted animate-pulse rounded" />
                <div className="h-4 w-24 bg-muted animate-pulse rounded" />
              </div>
              <div className="w-full bg-muted rounded-full h-2">
                <div
                  className="bg-muted animate-pulse h-2 rounded-full"
                  style={{ width: `${50 + i * 15}%` }}
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="h-4 w-32 bg-muted animate-pulse rounded" />
                <div className="h-4 w-28 bg-muted animate-pulse rounded" />
                <div className="h-4 w-36 bg-muted animate-pulse rounded" />
                <div className="h-4 w-24 bg-muted animate-pulse rounded" />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto max-w-4xl p-6 space-y-8">
      <h1 className="text-2xl font-bold">Career Change Analysis</h1>

      <CareerPivotPaywall paywall={paywall} pivots={pivots} walletBalance={walletBalance} unlocking={unlocking} handleUnlock={handleUnlock} onBuyCredits={() => router.push("/billing")} />

      {error && <RecoveryNotice message={error} retryLabel={pivotId ? "Retry connection" : "Back to form"} onRetry={() => { setError(null); setStarting(Boolean(pivotId)); setStreamAttempt((value) => value + 1); }} />}

      <CareerRiskReport risk={risk} />

      <CareerPivotRecommendations pivots={pivots} skillBridges={skillBridges} status={status} expandedRadar={expandedRadar} setExpandedRadar={setExpandedRadar} />

    </div>
  );
}

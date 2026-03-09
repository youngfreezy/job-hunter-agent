// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ExternalLink, Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { API_BASE, getSSEToken, getAuthHeaders } from "@/lib/api";
import GigScatterChart from "@/components/charts/GigScatterChart";

interface Gig {
  id: string;
  title: string;
  platform: string;
  url: string;
  client_name: string;
  budget_type: string;
  budget_min: number;
  budget_max: number;
  duration: string;
  description_snippet: string;
  posted_date: string;
  proposals_count: number;
  match_score: number;
}

interface Profile {
  platform: string;
  bio: string;
  headline: string;
  hourly_rate: number;
  skills_tags: string[];
}

export default function FreelanceResultPage() {
  const { id } = useParams<{ id: string }>();
  const [status, setStatus] = useState("connecting");
  const [statusMessage, setStatusMessage] = useState("Connecting...");
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [gigs, setGigs] = useState<Gig[]>([]);
  const [proposals, setProposals] = useState<Record<string, string>>({});
  const [expandedGig, setExpandedGig] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hasCredits, setHasCredits] = useState<boolean | null>(null);

  // Fetch wallet to determine paywall status
  useEffect(() => {
    async function checkWallet() {
      try {
        const auth = await getAuthHeaders();
        const res = await fetch(`${API_BASE}/api/billing/wallet`, { headers: auth });
        if (res.ok) {
          const data = await res.json();
          setHasCredits(data.balance > 0 || data.free_remaining > 0);
        }
      } catch {}
    }
    checkWallet();
  }, []);

  useEffect(() => {
    let es: EventSource | null = null;

    async function connect() {
      const token = await getSSEToken();
      const sep = token ? `?token=${encodeURIComponent(token)}` : "";
      es = new EventSource(`${API_BASE}/api/freelance/${id}/stream${sep}`);

      es.addEventListener("status", (e) => {
        const data = JSON.parse(e.data);
        setStatus(data.status);
        setStatusMessage(data.message);
      });

      es.addEventListener("profiles_ready", (e) => {
        setProfiles(JSON.parse(e.data).profiles || []);
      });

      es.addEventListener("gigs_found", (e) => {
        const data = JSON.parse(e.data);
        setGigs(data.gigs || []);
      });

      es.addEventListener("proposals_ready", (e) => {
        setProposals(JSON.parse(e.data).proposals || {});
      });

      es.addEventListener("done", () => {
        setStatus("completed");
        setStatusMessage("Search complete!");
        es?.close();
      });

      es.addEventListener("error", (e) => {
        if (e instanceof MessageEvent) {
          setError(JSON.parse(e.data).message);
        }
        es?.close();
      });

      es.onerror = () => es?.close();
    }

    connect();
    return () => es?.close();
  }, [id]);

  function matchColor(score: number) {
    if (score >= 85) return "text-green-500";
    if (score >= 70) return "text-yellow-500";
    return "text-muted-foreground";
  }

  function downloadCoverLetter(gig: Gig, proposalText: string) {
    const content = `Cover Letter\n\nRe: ${gig.title}\nPlatform: ${gig.platform}\nClient: ${gig.client_name}\n\n---\n\n${proposalText}\n`;
    const blob = new Blob([content], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `cover-letter-${gig.title.toLowerCase().replace(/\s+/g, "-")}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="container mx-auto max-w-4xl p-6 space-y-8">
      <h1 className="text-2xl font-bold">Freelance Gigs</h1>

      {/* Status */}
      {status !== "completed" && !error && (
        <div className="bg-card border rounded-lg p-6 text-center">
          <div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full mx-auto mb-4" />
          <p className="text-muted-foreground">{statusMessage}</p>
        </div>
      )}

      {error && (
        <div className="bg-destructive/10 border border-destructive rounded-lg p-4">
          <p className="text-destructive">{error}</p>
        </div>
      )}

      {/* Profiles */}
      {profiles.length > 0 && (
        <details className="bg-card border rounded-lg p-4">
          <summary className="cursor-pointer font-medium">
            Your Freelance Profiles ({profiles.length} platforms)
          </summary>
          <div className="mt-4 space-y-4">
            {profiles.map((p, i) => (
              <div key={i} className="border-l-2 border-primary pl-4">
                <p className="font-medium capitalize">{p.platform}</p>
                <p className="text-sm text-muted-foreground">{p.headline}</p>
                <p className="text-sm">${p.hourly_rate}/hr</p>
                <div className="flex flex-wrap gap-1 mt-1">
                  {p.skills_tags.slice(0, 6).map((tag, j) => (
                    <span
                      key={j}
                      className="text-xs bg-muted px-2 py-0.5 rounded"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </details>
      )}

      {/* Gig Scatter Chart */}
      <GigScatterChart gigs={gigs} />

      {/* Gigs */}
      {gigs.length > 0 && (
        <div className="space-y-4">
          <h2 className="text-xl font-semibold">
            {gigs.length} Matching Gigs Found
          </h2>
          {gigs.map((gig) => (
            <div key={gig.id} className="bg-card border rounded-lg p-5 space-y-3">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-semibold">{gig.title}</h3>
                  <p className="text-sm text-muted-foreground">
                    {gig.platform} · {gig.client_name} · {gig.posted_date}
                  </p>
                </div>
                <span className={`text-sm font-bold ${matchColor(gig.match_score)}`}>
                  {Math.round(gig.match_score)}% match
                </span>
              </div>

              <div className="flex gap-4 text-sm">
                <span>
                  {gig.budget_type === "fixed" ? "Fixed" : "Hourly"}: $
                  {gig.budget_min?.toLocaleString()}
                  {gig.budget_max ? ` - $${gig.budget_max.toLocaleString()}` : ""}
                </span>
                {gig.duration && <span>· {gig.duration}</span>}
                {gig.proposals_count != null && (
                  <span>· {gig.proposals_count} proposals</span>
                )}
              </div>

              {gig.description_snippet && (
                <p className="text-sm text-muted-foreground">
                  {gig.description_snippet}
                </p>
              )}

              {/* Action buttons */}
              <div className="flex items-center gap-2 pt-1">
                {gig.url && (
                  <a
                    href={gig.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 text-sm text-primary hover:underline"
                  >
                    View Posting <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                )}

                {proposals[gig.id] && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      setExpandedGig(expandedGig === gig.id ? null : gig.id)
                    }
                  >
                    {expandedGig === gig.id ? "Hide Proposal" : "View Proposal"}
                  </Button>
                )}

                {proposals[gig.id] && (
                  hasCredits ? (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => downloadCoverLetter(gig, proposals[gig.id])}
                    >
                      Download Cover Letter
                    </Button>
                  ) : (
                    <Link href="/billing">
                      <Button variant="outline" size="sm" className="text-muted-foreground">
                        <Lock className="h-3.5 w-3.5 mr-1.5" />
                        Cover Letter
                      </Button>
                    </Link>
                  )
                )}
              </div>

              {/* Expanded proposal */}
              {expandedGig === gig.id && proposals[gig.id] && (
                hasCredits ? (
                  <div className="bg-muted/50 border rounded p-4 text-sm whitespace-pre-wrap">
                    {proposals[gig.id]}
                  </div>
                ) : (
                  <div className="relative">
                    <div className="bg-muted/50 border rounded p-4 text-sm whitespace-pre-wrap blur-sm select-none" aria-hidden>
                      {proposals[gig.id]}
                    </div>
                    <div className="absolute inset-0 flex items-center justify-center">
                      <Link href="/billing">
                        <Button>
                          <Lock className="h-4 w-4 mr-2" />
                          Unlock with Credits
                        </Button>
                      </Link>
                    </div>
                  </div>
                )
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

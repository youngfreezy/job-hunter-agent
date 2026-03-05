"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { listSessions, type SessionListItem } from "@/lib/api";

const STATUS_LABELS: Record<string, string> = {
  intake: "Starting",
  coaching: "Coaching",
  discovering: "Discovering",
  scoring: "Scoring",
  tailoring: "Tailoring",
  applying: "Applying",
  awaiting_coach_review: "Needs Review",
  awaiting_review: "Needs Review",
  paused: "Paused",
  completed: "Completed",
  failed: "Failed",
};

const STATUS_COLORS: Record<string, string> = {
  completed: "default",
  applying: "secondary",
  failed: "destructive",
  paused: "outline",
  intake: "outline",
  coaching: "secondary",
  discovering: "secondary",
  scoring: "secondary",
  tailoring: "secondary",
  awaiting_coach_review: "outline",
  awaiting_review: "outline",
};

export default function Dashboard() {
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listSessions()
      .then(setSessions)
      .catch((err) => console.error("Failed to load sessions:", err))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-white dark:bg-zinc-950">
      <nav className="border-b border-zinc-200 dark:border-zinc-800 px-6 py-4 flex items-center justify-between max-w-7xl mx-auto">
        <Link href="/" className="text-xl font-bold tracking-tight">
          JobHunter Agent
        </Link>
        <div className="flex items-center gap-4">
          <span className="text-sm text-zinc-500">test@example.com</span>
          <Link href="/session/new">
            <Button size="sm">New Session</Button>
          </Link>
        </div>
      </nav>

      <div className="max-w-5xl mx-auto px-6 py-12">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold">Dashboard</h1>
            <p className="text-zinc-600 dark:text-zinc-400 mt-1">
              Your job hunting sessions
            </p>
          </div>
          <Link href="/session/new">
            <Button>Start New Session</Button>
          </Link>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-4 gap-4 mb-8">
          {loading ? (
            [1, 2, 3, 4].map((i) => (
              <Card key={i}>
                <CardContent className="pt-6">
                  <div className="h-7 w-12 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse mb-2" />
                  <div className="h-3 w-24 bg-zinc-100 dark:bg-zinc-900 rounded animate-pulse" />
                </CardContent>
              </Card>
            ))
          ) : (
            <>
              <Card>
                <CardContent className="pt-6">
                  <p className="text-2xl font-bold">{sessions.length}</p>
                  <p className="text-sm text-zinc-500">Total Sessions</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-6">
                  <p className="text-2xl font-bold">
                    {sessions.reduce(
                      (sum, s) => sum + s.applications_submitted,
                      0
                    )}
                  </p>
                  <p className="text-sm text-zinc-500">Applications Sent</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-6">
                  <p className="text-2xl font-bold">
                    {sessions.filter((s) => s.status === "completed").length}
                  </p>
                  <p className="text-sm text-zinc-500">Completed</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-6">
                  <p className="text-2xl font-bold">Professional</p>
                  <p className="text-sm text-zinc-500">Current Plan</p>
                </CardContent>
              </Card>
            </>
          )}
        </div>

        {/* Sessions list */}
        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="rounded-lg border border-zinc-200 dark:border-zinc-800 p-4 flex items-center justify-between"
              >
                <div className="space-y-2">
                  <div className="h-5 w-48 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse" />
                  <div className="h-3 w-32 bg-zinc-100 dark:bg-zinc-900 rounded animate-pulse" />
                </div>
                <div className="h-6 w-20 bg-zinc-200 dark:bg-zinc-800 rounded-full animate-pulse" />
              </div>
            ))}
          </div>
        ) : sessions.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center">
              <p className="text-zinc-500 mb-4">
                No sessions yet. Start your first job hunt!
              </p>
              <Link href="/session/new">
                <Button>Start Session</Button>
              </Link>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {sessions.map((s) => (
              <Link key={s.session_id} href={`/session/${s.session_id}`}>
                <Card className="hover:border-zinc-400 dark:hover:border-zinc-600 transition-colors cursor-pointer">
                  <CardContent className="py-4 flex items-center justify-between">
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <Badge
                          variant={
                            (STATUS_COLORS[s.status] as
                              | "default"
                              | "secondary"
                              | "destructive"
                              | "outline") || "secondary"
                          }
                        >
                          {STATUS_LABELS[s.status] || s.status}
                        </Badge>
                        <span className="text-sm text-zinc-500">
                          {new Date(s.created_at).toLocaleDateString()}
                        </span>
                      </div>
                      <p className="font-medium">{s.keywords.join(", ")}</p>
                    </div>
                    <div className="text-right text-sm">
                      <p>
                        <span className="text-green-600">
                          {s.applications_submitted}
                        </span>{" "}
                        submitted
                      </p>
                      {s.applications_failed > 0 && (
                        <p>
                          <span className="text-red-500">
                            {s.applications_failed}
                          </span>{" "}
                          failed
                        </p>
                      )}
                    </div>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

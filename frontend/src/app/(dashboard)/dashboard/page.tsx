// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { MoreHorizontal, Search } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageContainer, PageHeader } from "@/components/ui/page-header";
import { StatusDot } from "@/components/ui/status-dot";
import { PipelineLedger } from "@/components/run/PipelineLedger";
import { AdjustDialog } from "@/components/run/AdjustDialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  archiveSession,
  getWallet,
  killSession,
  listSessions,
  rerunSession,
  resumeSession,
  type SessionListItem,
} from "@/lib/api";
import {
  NEEDS_YOU,
  PHASES,
  TERMINAL,
  buildLedger,
  currentPhase,
  formatStarted,
  runName,
  runOutcome,
} from "@/lib/run";

type Wallet = { balance: number; free_remaining: number };

function creditsSentence(w: Wallet | null) {
  if (!w) return null;
  const credits = Math.floor(w.balance);
  return (
    <>
      You have <span className="font-mono text-foreground">{credits}</span>{" "}
      {credits === 1 ? "credit" : "credits"}
      {w.free_remaining > 0 && (
        <>
          {" "}
          and <span className="font-mono text-foreground">{w.free_remaining}</span> free{" "}
          {w.free_remaining === 1 ? "application" : "applications"}
        </>
      )}
      .{" "}
      <Link href="/billing" className="font-medium text-primary hover:underline">
        Buy credits
      </Link>
    </>
  );
}

function costSentence(w: Wallet | null) {
  const base = "You approve the shortlist before anything is sent. Each application sent costs 1 credit.";
  if (!w) return base;
  const left = Math.floor(w.balance) + w.free_remaining;
  return left === 0
    ? `${base} You have no credits or free applications left, so the run will stop at the shortlist.`
    : `${base} You can send up to ${left} with your current balance.`;
}

const WAITING_COPY: Record<string, { text: (name: string) => string; action: string }> = {
  awaiting_coach_review: { text: (n) => `Coached resume ready for ${n}`, action: "Review resume" },
  awaiting_review: { text: (n) => `Shortlist ready for ${n}`, action: "Review shortlist" },
  needs_intervention: { text: (n) => `${n} needs your help with an application`, action: "Open run" },
  paused: { text: (n) => `${n} is paused`, action: "Resume" },
};

function ledgerFor(s: SessionListItem) {
  return buildLedger({
    status: s.status,
    submitted: s.applications_submitted,
    failed: s.applications_failed,
    attempted: TERMINAL.has(s.status) ? s.applications_submitted + s.applications_failed : null,
  });
}

function phaseCaption(s: SessionListItem) {
  if (TERMINAL.has(s.status)) return undefined;
  const key = currentPhase(s.status);
  const i = PHASES.findIndex((p) => p.key === key);
  return `${PHASES[i].label} · ${i + 1} of 5`;
}

export default function Home() {
  const router = useRouter();
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [query, setQuery] = useState("");
  const [rerunTarget, setRerunTarget] = useState<SessionListItem | null>(null);
  const [adjustTarget, setAdjustTarget] = useState<SessionListItem | null>(null);
  const [stopTarget, setStopTarget] = useState<SessionListItem | null>(null);
  const [busy, setBusy] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchSessions = useCallback(() => {
    listSessions()
      .then((s) => {
        setSessions(s);
        setLoadError(false);
      })
      .catch(() => setLoadError(true))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    document.title = "Home · JobHunter";
    fetchSessions();
    getWallet().then(setWallet).catch(() => setWallet(null));
  }, [fetchSessions]);

  const hasActive = sessions.some((s) => !TERMINAL.has(s.status));
  useEffect(() => {
    if (!hasActive) return;
    pollRef.current = setInterval(fetchSessions, 15000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [hasActive, fetchSessions]);

  const waiting = useMemo(
    () =>
      sessions
        .filter((s) => NEEDS_YOU.has(s.status))
        .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()),
    [sessions]
  );

  const runs = useMemo(() => {
    const q = query.trim().toLowerCase();
    const sorted = [...sessions].sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    );
    if (!q) return sorted;
    return sorted.filter((s) =>
      [runName(s), ...(s.keywords ?? []), ...(s.locations ?? [])].join(" ").toLowerCase().includes(q)
    );
  }, [sessions, query]);

  async function startRerun(s: SessionListItem, overrides?: Parameters<typeof rerunSession>[1]) {
    setBusy(true);
    try {
      const { session_id } = await rerunSession(s.session_id, overrides);
      setRerunTarget(null);
      setAdjustTarget(null);
      router.push(`/session/${session_id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't start the run. Try again in a minute.");
    } finally {
      setBusy(false);
    }
  }

  async function stopRun(s: SessionListItem) {
    setBusy(true);
    try {
      await killSession(s.session_id);
      toast("Run stopped. Applications already sent are kept.");
      setStopTarget(null);
      fetchSessions();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't stop the run.");
    } finally {
      setBusy(false);
    }
  }

  async function archive(s: SessionListItem) {
    try {
      await archiveSession(s.session_id, true);
      setSessions((prev) => prev.filter((x) => x.session_id !== s.session_id));
      toast("Run archived", {
        action: {
          label: "Undo",
          onClick: async () => {
            await archiveSession(s.session_id, false).catch(() => {});
            fetchSessions();
          },
        },
      });
    } catch {
      toast.error("Couldn't archive the run.");
    }
  }

  async function resume(s: SessionListItem) {
    try {
      await resumeSession(s.session_id);
      router.push(`/session/${s.session_id}`);
    } catch {
      toast.error("Couldn't resume the run. Open it to see what it needs.");
    }
  }

  function RowActions({ s }: { s: SessionListItem }) {
    const finished = TERMINAL.has(s.status);
    const nothingSent = finished && s.applications_submitted === 0;
    const name = runName(s);
    return (
      <div className="flex items-center justify-end gap-1.5">
        {NEEDS_YOU.has(s.status) ? (
          <Button asChild size="sm">
            <Link href={`/session/${s.session_id}`}>{WAITING_COPY[s.status]?.action ?? "Open"}</Link>
          </Button>
        ) : finished ? (
          <Button
            size="sm"
            variant="outline"
            onClick={() => (nothingSent ? setAdjustTarget(s) : setRerunTarget(s))}
          >
            {nothingSent ? "Adjust search" : "Run again"}
          </Button>
        ) : (
          <Button asChild size="sm" variant="outline">
            <Link href={`/session/${s.session_id}`}>Open</Link>
          </Button>
        )}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size="icon" variant="ghost" className="h-8 w-8" aria-label={`More actions for ${name}`}>
              <MoreHorizontal className="h-4 w-4" aria-hidden="true" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            <DropdownMenuItem asChild>
              <Link href={`/session/${s.session_id}`}>Open run</Link>
            </DropdownMenuItem>
            {finished && (
              <>
                <DropdownMenuItem onSelect={() => setRerunTarget(s)}>Run again</DropdownMenuItem>
                <DropdownMenuItem onSelect={() => setAdjustTarget(s)}>Adjust and run</DropdownMenuItem>
              </>
            )}
            <DropdownMenuItem asChild>
              <Link href={`/session/${s.session_id}/manual-apply`}>Applications</Link>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            {finished ? (
              <DropdownMenuItem onSelect={() => void archive(s)}>Archive</DropdownMenuItem>
            ) : (
              <DropdownMenuItem className="text-destructive" onSelect={() => setStopTarget(s)}>
                Stop run
              </DropdownMenuItem>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    );
  }

  return (
    <PageContainer>
      <PageHeader
        title="Home"
        description={creditsSentence(wallet) ?? " "}
        actions={
          <Button asChild variant="outline">
            <Link href="/quick-apply">Paste job links</Link>
          </Button>
        }
      />

      <section aria-labelledby="waiting-h" className="mb-8">
        <h2 id="waiting-h" className="mb-2 text-base font-semibold">
          Waiting on you
        </h2>
        {loading ? (
          <div className="h-16 rounded-xl border border-border bg-card" />
        ) : waiting.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nothing is waiting on you.</p>
        ) : (
          <ul className="divide-y divide-border overflow-hidden rounded-xl border border-warning-border bg-card">
            {waiting.map((s) => {
              const copy = WAITING_COPY[s.status];
              return (
                <li key={s.session_id} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
                  <span aria-hidden="true" className="h-2 w-2 shrink-0 rounded-full bg-warning-border ring-1 ring-warning" />
                  <div className="min-w-0 flex-1 basis-64">
                    <p className="font-medium">{copy.text(runName(s))}</p>
                    <p className="text-[13px] text-muted-foreground">
                      Started {formatStarted(s.created_at)}. Nothing is sent until you approve.
                    </p>
                  </div>
                  {s.status === "paused" ? (
                    <Button size="sm" onClick={() => void resume(s)}>
                      Resume
                    </Button>
                  ) : (
                    <Button asChild size="sm">
                      <Link href={`/session/${s.session_id}`}>{copy.action}</Link>
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section aria-labelledby="runs-h">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 id="runs-h" className="text-base font-semibold">
            Runs
          </h2>
          <label className="relative w-full sm:w-64">
            <span className="sr-only">Search runs</span>
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
            <Input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by role or place"
              className="pl-9"
            />
          </label>
        </div>

        {loadError ? (
          <div className="rounded-xl border border-border bg-card px-4 py-6 text-sm">
            <p className="font-medium">Couldn&apos;t load your runs.</p>
            <p className="mt-1 text-muted-foreground">
              Your runs are safe. Check your connection and try again.
            </p>
            <Button className="mt-3" size="sm" variant="outline" onClick={fetchSessions}>
              Try again
            </Button>
          </div>
        ) : loading ? (
          <div className="overflow-hidden rounded-xl border border-border bg-card">
            {[0, 1, 2].map((i) => (
              <div key={i} className="flex h-14 items-center gap-4 border-t border-border px-4 first:border-t-0">
                <div className="h-3 w-56 rounded bg-muted" />
                <div className="ml-auto h-3 w-24 rounded bg-muted" />
              </div>
            ))}
          </div>
        ) : sessions.length === 0 ? (
          <div className="rounded-xl border border-border bg-card px-4 py-6 text-sm">
            <p className="font-medium">No runs yet.</p>
            <p className="mt-1 text-muted-foreground">
              A run searches job boards for your roles, ranks the postings and asks you to approve a
              shortlist before it applies.
            </p>
            <Button asChild className="mt-3" size="sm">
              <Link href="/session/new">Start a search</Link>
            </Button>
          </div>
        ) : runs.length === 0 ? (
          <p className="rounded-xl border border-border bg-card px-4 py-6 text-sm text-muted-foreground">
            No runs match &ldquo;{query}&rdquo;.
          </p>
        ) : (
          <>
            {/* Table from 640px */}
            <div className="hidden overflow-x-auto rounded-xl border border-border bg-card sm:block">
              <table className="w-full min-w-[760px] border-collapse text-[13px]">
                <thead className="bg-surface-2 text-left text-muted-foreground">
                  <tr>
                    <th scope="col" className="px-4 py-2.5 font-medium">Run</th>
                    <th scope="col" className="px-3 py-2.5 font-medium">Started</th>
                    <th scope="col" className="px-3 py-2.5 font-medium">Pipeline</th>
                    <th scope="col" className="px-3 py-2.5 text-right font-medium">Sent</th>
                    <th scope="col" className="px-4 py-2.5">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((s) => {
                    const outcome = runOutcome({
                      status: s.status,
                      submitted: s.applications_submitted,
                      failed: s.applications_failed,
                    });
                    const { phases, gates } = ledgerFor(s);
                    return (
                      <tr key={s.session_id} className="border-t border-border transition-colors hover:bg-surface-2/60">
                        <td className="px-4 py-2.5">
                          <Link
                            href={`/session/${s.session_id}`}
                            className="block text-sm font-medium text-foreground hover:text-primary"
                          >
                            {runName(s)}
                          </Link>
                          <StatusDot tone={outcome.tone}>{outcome.label}</StatusDot>
                        </td>
                        <td className="whitespace-nowrap px-3 py-2.5 font-mono text-muted-foreground">
                          <time dateTime={s.created_at}>{formatStarted(s.created_at)}</time>
                        </td>
                        <td className="px-3 py-2.5">
                          <PipelineLedger compact phases={phases} gates={gates} caption={phaseCaption(s)} />
                        </td>
                        <td className="px-3 py-2.5 text-right font-mono text-sm">
                          {s.applications_submitted}
                        </td>
                        <td className="px-4 py-2.5">
                          <RowActions s={s} />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Stacked rows on phones */}
            <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-card sm:hidden">
              {runs.map((s) => {
                const outcome = runOutcome({
                  status: s.status,
                  submitted: s.applications_submitted,
                  failed: s.applications_failed,
                });
                const { phases, gates } = ledgerFor(s);
                return (
                  <li key={s.session_id} className="flex flex-col gap-2 px-4 py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <Link href={`/session/${s.session_id}`} className="block font-medium">
                          {runName(s)}
                        </Link>
                        <p className="font-mono text-xs text-muted-foreground">
                          {formatStarted(s.created_at)} · {s.applications_submitted} sent
                        </p>
                      </div>
                    </div>
                    <StatusDot tone={outcome.tone}>{outcome.label}</StatusDot>
                    <PipelineLedger compact phases={phases} gates={gates} className="max-w-none" />
                    <RowActions s={s} />
                  </li>
                );
              })}
            </ul>
            <p className="mt-2 text-xs text-muted-foreground">
              {sessions.length} {sessions.length === 1 ? "run" : "runs"}.{" "}
              <Link href="/history" className="hover:text-foreground hover:underline">
                See archived runs
              </Link>
            </p>
          </>
        )}
      </section>

      {/* Run again: show the cost before spending anything */}
      <Dialog open={!!rerunTarget} onOpenChange={(o) => !o && setRerunTarget(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Run {rerunTarget ? runName(rerunTarget) : ""} again</DialogTitle>
            <DialogDescription>{costSentence(wallet)}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRerunTarget(null)}>
              Cancel
            </Button>
            <Button loading={busy} onClick={() => rerunTarget && void startRerun(rerunTarget)}>
              Start run
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {adjustTarget && (
        <AdjustDialog
          run={adjustTarget}
          busy={busy}
          costLine={costSentence(wallet)}
          onCancel={() => setAdjustTarget(null)}
          onStart={(o) => void startRerun(adjustTarget, o)}
        />
      )}

      <Dialog open={!!stopTarget} onOpenChange={(o) => !o && setStopTarget(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Stop {stopTarget ? runName(stopTarget) : ""}?</DialogTitle>
            <DialogDescription>
              The agent stops after its current step. Applications already sent stay sent, and you
              aren&apos;t charged for jobs it didn&apos;t reach.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setStopTarget(null)}>
              Keep running
            </Button>
            <Button variant="destructive" loading={busy} onClick={() => stopTarget && void stopRun(stopTarget)}>
              Stop run
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageContainer>
  );
}

// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { LiveBrowserPanel } from "@/components/LiveBrowserPanel";

import {
  API_BASE,
  getAuthHeaders,
  apiFetch,
  updateApplicationRules,
  updateMinimumSubmitted,
  getBrowserbaseSettings,
  saveBrowserbaseSettings,
  startBrowserbaseLogin,
  getBrowserbaseLogin,
  cancelBrowserbaseLogin,
  type BrowserbaseSettings,
  type BrowserbaseLoginSession,
} from "@/lib/api";

const BROWSERBASE_BOARD_LABELS: Record<string, string> = {
  indeed: "Indeed",
  glassdoor: "Glassdoor",
  ziprecruiter: "ZipRecruiter",
  default: "Default (any other board)",
};

const APPLICATION_RULES_MAX = 20000;

const APPLICATION_RULES_PLACEHOLDER = `Eligibility: remote (US) or Austin, TX only. Senior/Staff level. Python or TypeScript stacks. Base pay at least $180k.
Standard answers: work authorization = yes, sponsorship = no, how did you hear = job board.
Park and ask me: any question aimed at AI tools or agents, "write this in your own words" essays, any attestation that no AI was used.
Never invent facts about me that are not in my resume.`;

export default function SettingsPage() {
  const [phone, setPhone] = useState("");
  const [phoneVerified, setPhoneVerified] = useState(false);
  const [savedPhone, setSavedPhone] = useState<string | null>(null);
  const [notificationChannel, setNotificationChannel] = useState("email");
  const [verificationCode, setVerificationCode] = useState("");
  const [verifyStep, setVerifyStep] = useState<"input" | "code" | "done">("input");
  const [sending, setSending] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [savingChannel, setSavingChannel] = useState(false);
  const [loading, setLoading] = useState(true);
  const [blockedCompanies, setBlockedCompanies] = useState<string[]>([]);
  const [newCompany, setNewCompany] = useState("");
  const [savingBlocklist, setSavingBlocklist] = useState(false);
  const [isPremium, setIsPremium] = useState(false);
  const [minimumSubmitted, setMinimumSubmitted] = useState(0);
  const [savingMinSubmitted, setSavingMinSubmitted] = useState(false);
  const [browserbase, setBrowserbase] = useState<BrowserbaseSettings | null>(null);
  const [bbApiKey, setBbApiKey] = useState("");
  const [bbProjectId, setBbProjectId] = useState("");
  const [bbProxies, setBbProxies] = useState(false);
  const [bbContextIds, setBbContextIds] = useState<Record<string, string>>({});
  const [savingBrowserbase, setSavingBrowserbase] = useState(false);
  const [loginSession, setLoginSession] = useState<BrowserbaseLoginSession | null>(null);
  const [startingLogin, setStartingLogin] = useState<string | null>(null);
  const [applicationRules, setApplicationRules] = useState("");
  const [savedApplicationRules, setSavedApplicationRules] = useState("");
  const [savingRules, setSavingRules] = useState(false);


  useEffect(() => {
    async function load() {
      try {
        const auth = await getAuthHeaders();
        const res = await apiFetch(`${API_BASE}/api/auth/me`, { headers: auth });
        if (res.ok) {
          const data = await res.json();
          const user = data.user || data;
          setSavedPhone(user.phone_number || null);
          setPhoneVerified(user.phone_verified || false);
          setNotificationChannel(user.notification_channel || "email");
          setBlockedCompanies(user.blocked_companies || []);
          setIsPremium(user.is_premium || false);
          setMinimumSubmitted(user.minimum_submitted_applications || 0);
          setApplicationRules(user.application_rules || "");
          setSavedApplicationRules(user.application_rules || "");
          if (user.phone_verified) {
            setVerifyStep("done");
            setPhone(user.phone_number || "");
          }
        }
      } catch {
        console.error("Failed to load user settings");
      }

      try {
        const bb = await getBrowserbaseSettings();
        setBrowserbase(bb);
        setBbProjectId(bb.project_id || "");
        setBbProxies(bb.proxies);
        setBbContextIds(bb.context_ids || {});
      } catch {
        console.error("Failed to load Browserbase settings");
      }

      setLoading(false);
    }
    load();
  }, []);

  // Poll an in-flight "Sign in to <board>" capture until the backend stores the Context.
  useEffect(() => {
    if (!loginSession || loginSession.status !== "waiting") return;
    const captureId = loginSession.capture_id;
    const timer = setInterval(async () => {
      try {
        const next = await getBrowserbaseLogin(captureId);
        setLoginSession(next);
        if (next.status === "captured" && next.context_id) {
          setBbContextIds((prev) => ({ ...prev, [next.board]: next.context_id as string }));
          toast.success(`${BROWSERBASE_BOARD_LABELS[next.board] || next.board} login saved to a persisted Context`);
        } else if (next.status === "timeout" || next.status === "error") {
          toast.error(next.error || `Login capture ${next.status}`);
        }
      } catch {
        // transient; keep polling
      }
    }, 3000);
    return () => clearInterval(timer);
  }, [loginSession]);

  async function handleSendCode() {
    if (!phone.trim()) return;
    setSending(true);
    try {
      const auth = await getAuthHeaders();
      const res = await apiFetch(`${API_BASE}/api/sms/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({ phone_number: phone }),
      });
      if (res.ok) {
        setVerifyStep("code");
      } else {
        alert("Failed to send verification code");
      }
    } catch {
      alert("Failed to send verification code");
    } finally {
      setSending(false);
    }
  }

  async function handleConfirmCode() {
    if (!verificationCode.trim()) return;
    setConfirming(true);
    try {
      const auth = await getAuthHeaders();
      const res = await apiFetch(`${API_BASE}/api/sms/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({ code: verificationCode }),
      });
      if (res.ok) {
        setVerifyStep("done");
        setPhoneVerified(true);
        setSavedPhone(phone);
        toast.success("Phone number verified");
      } else {
        const data = await res.json().catch(() => ({}));
        alert(data.detail || "Invalid verification code");
      }
    } catch {
      alert("Verification failed");
    } finally {
      setConfirming(false);
    }
  }

  async function handleSaveChannel(channel: string) {
    setSavingChannel(true);
    try {
      const auth = await getAuthHeaders();
      await apiFetch(`${API_BASE}/api/auth/me/notification-channel`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({ notification_channel: channel }),
      });
      setNotificationChannel(channel);
    } catch {
      console.error("Failed to save notification preference");
    } finally {
      setSavingChannel(false);
    }
  }

  async function saveBlockedCompanies(updated: string[]) {
    setSavingBlocklist(true);
    try {
      const auth = await getAuthHeaders();
      await apiFetch(`${API_BASE}/api/auth/me/blocked-companies`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({ blocked_companies: updated }),
      });
      setBlockedCompanies(updated);
    } catch {
      toast.error("Failed to update company blocklist");
    } finally {
      setSavingBlocklist(false);
    }
  }

  function handleAddCompany() {
    const name = newCompany.trim();
    if (!name) return;
    if (blockedCompanies.some((c) => c.toLowerCase() === name.toLowerCase())) {
      toast.error(`${name} is already blocked`);
      return;
    }
    const updated = [...blockedCompanies, name];
    setNewCompany("");
    saveBlockedCompanies(updated);
    toast.success(`${name} added to blocklist`);
  }

  async function handleSaveMinSubmitted(value: number) {
    setSavingMinSubmitted(true);
    try {
      await updateMinimumSubmitted(value);
      setMinimumSubmitted(value);
      toast.success(value > 0 ? `Minimum set to ${value} submitted applications` : "Minimum submitted disabled");
    } catch {
      toast.error("Failed to save minimum submitted preference");
    } finally {
      setSavingMinSubmitted(false);
    }
  }

  async function handleSaveBrowserbase() {
    setSavingBrowserbase(true);
    try {
      const saved = await saveBrowserbaseSettings({
        ...(bbApiKey.trim() ? { api_key: bbApiKey.trim() } : {}),
        project_id: bbProjectId.trim(),
        proxies: bbProxies,
        context_ids: bbContextIds,
      });
      setBrowserbase(saved);
      setBbContextIds(saved.context_ids || {});
      setBbApiKey("");
      toast.success("Browserbase settings saved");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to save Browserbase settings");
    } finally {
      setSavingBrowserbase(false);
    }
  }

  async function handleClearBrowserbaseKey() {
    setSavingBrowserbase(true);
    try {
      const saved = await saveBrowserbaseSettings({
        api_key: "",
        project_id: bbProjectId.trim(),
        proxies: bbProxies,
        context_ids: bbContextIds,
      });
      setBrowserbase(saved);
      setBbApiKey("");
      toast.success("Browserbase API key removed");
    } catch {
      toast.error("Failed to remove Browserbase API key");
    } finally {
      setSavingBrowserbase(false);
    }
  }

  async function handleStartBrowserbaseLogin(board: string) {
    setStartingLogin(board);
    try {
      const session = await startBrowserbaseLogin(board);
      setLoginSession(session);
      toast.info(`Sign in to ${BROWSERBASE_BOARD_LABELS[board] || board} in the live browser below`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to start login session");
    } finally {
      setStartingLogin(null);
    }
  }

  async function handleCancelBrowserbaseLogin() {
    if (!loginSession) return;
    try {
      await cancelBrowserbaseLogin(loginSession.capture_id);
    } catch {
      // the capture times out on its own
    }
    setLoginSession(null);
  }

  async function handleSaveApplicationRules() {
    const rules = applicationRules.trim();
    if (rules.length > APPLICATION_RULES_MAX) {
      toast.error(`Rules must be at most ${APPLICATION_RULES_MAX.toLocaleString()} characters`);
      return;
    }
    setSavingRules(true);
    try {
      const saved = await updateApplicationRules(rules);
      setApplicationRules(saved.application_rules);
      setSavedApplicationRules(saved.application_rules);
      toast.success(saved.application_rules ? "Application rules saved" : "Application rules cleared");
    } catch {
      toast.error("Failed to save application rules");
    } finally {
      setSavingRules(false);
    }
  }

  function handleRemoveCompany(company: string) {
    const updated = blockedCompanies.filter((c) => c !== company);
    saveBlockedCompanies(updated);
    toast.success(`${company} removed from blocklist`);
  }

  if (loading) return null;

  return (
    <main className="mx-auto max-w-3xl px-4 py-10 space-y-8">
      <h1 className="text-2xl font-bold">Settings</h1>

      {/* Phone verification */}
      <Card>
        <CardHeader>
          <CardTitle>Phone Number</CardTitle>
          <CardDescription>
            Link your phone for SMS notifications and autopilot approvals via text.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {verifyStep === "input" && (
            <div className="flex gap-2">
              <input
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+1 (555) 123-4567"
                className="flex-1 rounded-md border px-3 py-2 text-sm bg-background"
              />
              <Button onClick={handleSendCode} disabled={sending || !phone.trim()}>
                {sending ? "Sending..." : "Send Code"}
              </Button>
            </div>
          )}

          {verifyStep === "code" && (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Enter the 6-digit code sent to {phone}
              </p>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={verificationCode}
                  onChange={(e) => setVerificationCode(e.target.value)}
                  placeholder="123456"
                  maxLength={6}
                  className="w-32 rounded-md border px-3 py-2 text-sm bg-background text-center tracking-widest"
                />
                <Button
                  onClick={handleConfirmCode}
                  disabled={confirming || verificationCode.length !== 6}
                >
                  {confirming ? "Verifying..." : "Verify"}
                </Button>
                <Button variant="outline" onClick={() => setVerifyStep("input")}>
                  Back
                </Button>
              </div>
            </div>
          )}

          {verifyStep === "done" && (
            <div className="flex items-center gap-3">
              <span className="text-sm font-medium">{savedPhone}</span>
              <Badge variant="default">Verified</Badge>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setVerifyStep("input");
                  setPhone("");
                  setVerificationCode("");
                }}
              >
                Change
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Notification preferences */}
      {phoneVerified && (
        <Card>
          <CardHeader>
            <CardTitle>Notification Preferences</CardTitle>
            <CardDescription>
              Choose how you want to receive session updates and autopilot approvals.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {(["email", "sms", "both"] as const).map((channel) => (
                <label
                  key={channel}
                  className={`flex items-center gap-3 rounded-lg border p-3 cursor-pointer transition-colors ${
                    notificationChannel === channel
                      ? "border-primary bg-primary/5"
                      : "hover:bg-muted/50"
                  }`}
                >
                  <input
                    type="radio"
                    name="channel"
                    value={channel}
                    checked={notificationChannel === channel}
                    onChange={() => handleSaveChannel(channel)}
                    disabled={savingChannel}
                    className="accent-primary"
                  />
                  <div>
                    <div className="text-sm font-medium capitalize">{channel}</div>
                    <div className="text-xs text-muted-foreground">
                      {channel === "email" && "Receive notifications via email only"}
                      {channel === "sms" && "Receive notifications via SMS only"}
                      {channel === "both" && "Receive notifications via both email and SMS"}
                    </div>
                  </div>
                </label>
              ))}
            </div>
          </CardContent>
        </Card>
      )}


      {/* Company blocklist */}
      <Card>
        <CardHeader>
          <CardTitle>Company Blocklist</CardTitle>
          <CardDescription>
            Companies you never want to see in job results. Applied to all sessions automatically.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-col sm:flex-row gap-2">
            <input
              type="text"
              value={newCompany}
              onChange={(e) => setNewCompany(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleAddCompany()}
              placeholder="e.g. Anthropic"
              className="flex-1 rounded-md border px-3 py-2 text-sm bg-background"
              disabled={savingBlocklist}
            />
            <Button
              onClick={handleAddCompany}
              disabled={savingBlocklist || !newCompany.trim()}
              size="sm"
            >
              Add
            </Button>
          </div>
          {blockedCompanies.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {blockedCompanies.map((company) => (
                <Badge
                  key={company}
                  variant="secondary"
                  className="gap-1 pr-1 text-sm"
                >
                  {company}
                  <button
                    onClick={() => handleRemoveCompany(company)}
                    disabled={savingBlocklist}
                    className="ml-1 rounded-full p-0.5 hover:bg-destructive/20 transition-colors"
                    aria-label={`Remove ${company}`}
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                  </button>
                </Badge>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              No companies blocked. Jobs from all companies will appear in your results.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Application rules */}
      <Card>
        <CardHeader>
          <CardTitle>Application Rules</CardTitle>
          <CardDescription>
            Plain-text rules the agent must obey when scoring jobs and filling forms: eligibility
            (location, seniority, stack, pay), standard answers, and when to park an application
            for you instead of answering. Applied to all sessions.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Textarea
            id="application-rules"
            aria-label="Application rules"
            value={applicationRules}
            onChange={(e) => setApplicationRules(e.target.value)}
            placeholder={APPLICATION_RULES_PLACEHOLDER}
            rows={10}
            maxLength={APPLICATION_RULES_MAX}
            disabled={savingRules}
            className="font-mono text-sm"
          />
          <div className="flex items-center justify-between gap-4">
            <p className="text-xs text-muted-foreground">
              {applicationRules.length.toLocaleString()} / {APPLICATION_RULES_MAX.toLocaleString()} characters.
              A parked application shows up as skipped with the exact question in its error.
            </p>
            <Button
              onClick={handleSaveApplicationRules}
              disabled={savingRules || applicationRules.trim() === savedApplicationRules}
              size="sm"
            >
              {savingRules ? "Saving..." : "Save rules"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Browserbase cloud browsers */}
      <Card>
        <CardHeader>
          <CardTitle>Browserbase</CardTitle>
          <CardDescription>
            Cloud browsers for applying (BROWSER_MODE=browserbase). Your key is stored encrypted and
            never shown again. Sign in to a job board once; the login is kept in a persisted Context
            that every later session reuses.
            {browserbase?.env_configured && !browserbase?.api_key_set && (
              <> A server-wide key is configured and will be used until you save your own.</>
            )}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="space-y-1 text-sm">
              <span className="font-medium">API key</span>
              <input
                type="password"
                autoComplete="off"
                value={bbApiKey}
                onChange={(e) => setBbApiKey(e.target.value)}
                placeholder={browserbase?.api_key_set ? `saved (${browserbase.api_key_hint})` : "bb_live_…"}
                className="w-full rounded-md border px-3 py-2 text-sm bg-background font-mono"
                disabled={savingBrowserbase}
              />
              {browserbase?.api_key_set && (
                <button
                  type="button"
                  onClick={handleClearBrowserbaseKey}
                  disabled={savingBrowserbase}
                  className="text-xs text-muted-foreground underline"
                >
                  Remove saved key
                </button>
              )}
            </label>
            <label className="space-y-1 text-sm">
              <span className="font-medium">Project id</span>
              <input
                type="text"
                value={bbProjectId}
                onChange={(e) => setBbProjectId(e.target.value)}
                placeholder="00000000-0000-0000-0000-000000000000"
                className="w-full rounded-md border px-3 py-2 text-sm bg-background font-mono"
                disabled={savingBrowserbase}
              />
            </label>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={bbProxies}
              onChange={(e) => setBbProxies(e.target.checked)}
              disabled={savingBrowserbase}
              className="accent-primary"
            />
            <span>Use Browserbase residential proxies (paid plans; needed for Indeed at volume)</span>
          </label>

          <div className="space-y-2">
            <p className="text-sm font-medium">Persisted login Contexts</p>
            <p className="text-xs text-muted-foreground">
              One Context id per board. Use &quot;Sign in&quot; to create one by logging in yourself,
              or paste an id from the Browserbase dashboard.
            </p>
            <div className="space-y-2">
              {(browserbase?.boards || Object.keys(BROWSERBASE_BOARD_LABELS)).map((board) => {
                const canCapture = (browserbase?.login_capture_boards || []).includes(board);
                const capturing = loginSession?.board === board && loginSession.status === "waiting";
                return (
                  <div key={board} className="flex flex-col gap-2 sm:flex-row sm:items-center">
                    <span className="w-full sm:w-44 text-sm">{BROWSERBASE_BOARD_LABELS[board] || board}</span>
                    <input
                      type="text"
                      value={bbContextIds[board] || ""}
                      onChange={(e) =>
                        setBbContextIds((prev) => ({ ...prev, [board]: e.target.value }))
                      }
                      placeholder={browserbase?.effective_context_ids?.[board] ? "Using saved server Context" : "context id"}
                      aria-label={`${BROWSERBASE_BOARD_LABELS[board] || board} context id`}
                      className="flex-1 rounded-md border px-3 py-2 text-sm bg-background font-mono"
                      disabled={savingBrowserbase}
                    />
                    {canCapture && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleStartBrowserbaseLogin(board)}
                        disabled={
                          startingLogin !== null || capturing || !browserbase?.effective_configured
                        }
                      >
                        {capturing ? "Waiting for login…" : `Sign in to ${BROWSERBASE_BOARD_LABELS[board] || board}`}
                      </Button>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {loginSession && (
            <div className="space-y-2">
              {loginSession.live_view_url && loginSession.status === "waiting" ? (
                <LiveBrowserPanel
                  liveView={{
                    url: loginSession.live_view_url,
                    provider: "browserbase",
                    browserbaseSessionId: loginSession.browserbase_session_id,
                    jobId: "",
                    receivedAt: new Date().toISOString(),
                  }}
                  jobLabel={`sign in to ${BROWSERBASE_BOARD_LABELS[loginSession.board] || loginSession.board}`}
                  onHide={handleCancelBrowserbaseLogin}
                />
              ) : null}
              <p className="text-xs text-muted-foreground">
                {loginSession.status === "waiting" &&
                  "Log in inside the browser above. Once the board's login cookie appears the browser closes and the Context id is filled in."}
                {loginSession.status === "captured" && "Login captured. Save to keep the Context id."}
                {(loginSession.status === "timeout" || loginSession.status === "error") &&
                  (loginSession.error || `Login capture ${loginSession.status}.`)}
                {loginSession.status === "cancelled" && "Login capture cancelled."}
              </p>
            </div>
          )}

          <div className="flex justify-end">
            <Button onClick={handleSaveBrowserbase} disabled={savingBrowserbase} size="sm">
              {savingBrowserbase ? "Saving..." : "Save Browserbase settings"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Minimum Submitted Applications (premium) */}
      {isPremium && (
        <Card>
          <CardHeader>
            <CardTitle>Minimum Submitted Applications</CardTitle>
            <CardDescription>
              Keep discovering and retrying until at least this many applications are actually submitted.
              Applied to all new sessions automatically.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-4">
              <input
                type="range"
                min={0}
                max={20}
                step={1}
                value={minimumSubmitted}
                onChange={(e) => {
                  const v = parseInt(e.target.value, 10);
                  setMinimumSubmitted(v);
                }}
                onMouseUp={() => handleSaveMinSubmitted(minimumSubmitted)}
                onTouchEnd={() => handleSaveMinSubmitted(minimumSubmitted)}
                disabled={savingMinSubmitted}
                className="flex-1 accent-primary"
              />
              <span className="text-lg font-bold tabular-nums w-8 text-center">
                {minimumSubmitted}
              </span>
            </div>
            <p className="text-xs text-muted-foreground">
              {minimumSubmitted === 0
                ? "Disabled — the agent will attempt each job once and move on."
                : `The agent will try additional matching jobs toward a target of ${minimumSubmitted} application${minimumSubmitted !== 1 ? "s are" : " is"} successfully submitted.`}
            </p>
          </CardContent>
        </Card>
      )}

      {/* SMS Commands reference */}
      {phoneVerified && (
        <Card>
          <CardHeader>
            <CardTitle>SMS Commands</CardTitle>
            <CardDescription>
              Text these commands to your JobHunter number to control sessions from your phone.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between py-1 border-b">
                <code className="font-mono text-primary">STATUS</code>
                <span className="text-muted-foreground">Check latest session status</span>
              </div>
              <div className="flex justify-between py-1 border-b">
                <code className="font-mono text-primary">APPROVE</code>
                <span className="text-muted-foreground">Approve pending autopilot jobs</span>
              </div>
              <div className="flex justify-between py-1 border-b">
                <code className="font-mono text-primary">REJECT</code>
                <span className="text-muted-foreground">Skip pending autopilot jobs</span>
              </div>
              <div className="flex justify-between py-1 border-b">
                <code className="font-mono text-primary">PAUSE</code>
                <span className="text-muted-foreground">Pause all autopilot schedules</span>
              </div>
              <div className="flex justify-between py-1 border-b">
                <code className="font-mono text-primary">RESUME</code>
                <span className="text-muted-foreground">Resume paused schedules</span>
              </div>
              <div className="flex justify-between py-1">
                <code className="font-mono text-primary">HELP</code>
                <span className="text-muted-foreground">List all commands</span>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </main>
  );
}

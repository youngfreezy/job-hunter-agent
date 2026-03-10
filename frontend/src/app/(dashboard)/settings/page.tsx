// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { API_BASE, getAuthHeaders, apiFetch } from "@/lib/api";

interface BoardCredential {
  board: string;
  has_credentials: boolean;
}

const BOARD_LABELS: Record<string, string> = {
  linkedin: "LinkedIn",
  indeed: "Indeed",
  glassdoor: "Glassdoor",
  ziprecruiter: "ZipRecruiter",
};

const BOARD_INFO: Record<string, { description: string; usernamePlaceholder: string; usernameLabel: string }> = {
  linkedin: {
    description: "Your LinkedIn email and password. Required for LinkedIn Easy Apply and jobs behind the login wall.",
    usernamePlaceholder: "your.email@example.com",
    usernameLabel: "LinkedIn Email",
  },
  indeed: {
    description: "Your Indeed account email and password. Required for Indeed applications that need sign-in.",
    usernamePlaceholder: "your.email@example.com",
    usernameLabel: "Indeed Email",
  },
  glassdoor: {
    description: "Your Glassdoor account email and password. Required for Glassdoor Easy Apply and authenticated listings.",
    usernamePlaceholder: "your.email@example.com",
    usernameLabel: "Glassdoor Email",
  },
  ziprecruiter: {
    description: "Your ZipRecruiter account email and password. Required for one-click apply and authenticated applications.",
    usernamePlaceholder: "your.email@example.com",
    usernameLabel: "ZipRecruiter Email",
  },
};

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

  // Board credentials
  const [boardCreds, setBoardCreds] = useState<BoardCredential[]>([]);
  const [editingBoard, setEditingBoard] = useState<string | null>(null);
  const [credUsername, setCredUsername] = useState("");
  const [credPassword, setCredPassword] = useState("");
  const [savingCred, setSavingCred] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        const auth = await getAuthHeaders();
        const res = await apiFetch(`${API_BASE}/api/auth/me`, { headers: auth });
        if (res.ok) {
          const user = await res.json();
          setSavedPhone(user.phone_number || null);
          setPhoneVerified(user.phone_verified || false);
          setNotificationChannel(user.notification_channel || "email");
          if (user.phone_verified) {
            setVerifyStep("done");
            setPhone(user.phone_number || "");
          }
        }
      } catch {
        console.error("Failed to load user settings");
      }

      // Load board credentials
      try {
        const auth = await getAuthHeaders();
        const credRes = await apiFetch(`${API_BASE}/api/credentials`, { headers: auth });
        if (credRes.ok) {
          setBoardCreds(await credRes.json());
        }
      } catch {
        console.error("Failed to load board credentials");
      }

      setLoading(false);
    }
    load();
  }, []);

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

  async function handleSaveCredential(board: string) {
    if (!credUsername.trim() || !credPassword.trim()) return;
    setSavingCred(true);
    try {
      const auth = await getAuthHeaders();
      const res = await apiFetch(`${API_BASE}/api/credentials`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({ board, username: credUsername, password: credPassword }),
      });
      if (res.ok) {
        setBoardCreds((prev) =>
          prev.map((c) => (c.board === board ? { ...c, has_credentials: true } : c))
        );
        setEditingBoard(null);
        setCredUsername("");
        setCredPassword("");
        toast.success(`${BOARD_LABELS[board] || board} credentials saved`);
      } else {
        const data = await res.json().catch(() => ({}));
        toast.error(data.detail || "Failed to save credentials");
      }
    } catch {
      toast.error("Failed to save credentials");
    } finally {
      setSavingCred(false);
    }
  }

  async function handleDeleteCredential(board: string) {
    try {
      const auth = await getAuthHeaders();
      const res = await apiFetch(`${API_BASE}/api/credentials/${board}`, {
        method: "DELETE",
        headers: auth,
      });
      if (res.ok) {
        setBoardCreds((prev) =>
          prev.map((c) => (c.board === board ? { ...c, has_credentials: false } : c))
        );
        toast.success(`${BOARD_LABELS[board] || board} credentials removed`);
      }
    } catch {
      toast.error("Failed to remove credentials");
    }
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

      {/* Board Credentials */}
      <Card>
        <CardHeader>
          <CardTitle>Job Board Credentials</CardTitle>
          <CardDescription>
            Save your login credentials so the AI agent can authenticate on job boards
            that require sign-in before applying. Credentials are encrypted at rest.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {boardCreds.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No job boards configured. Board credentials will appear here once the backend is connected.
            </p>
          )}
        </CardContent>
      </Card>

      {boardCreds.map((cred) => {
        const info = BOARD_INFO[cred.board];
        return (
          <Card key={cred.board}>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <CardTitle className="text-base">
                    {BOARD_LABELS[cred.board] || cred.board}
                  </CardTitle>
                  {cred.has_credentials && (
                    <Badge variant="default">Connected</Badge>
                  )}
                </div>
                <div className="flex gap-2">
                  {cred.has_credentials && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleDeleteCredential(cred.board)}
                    >
                      Remove
                    </Button>
                  )}
                  <Button
                    variant={cred.has_credentials ? "outline" : "default"}
                    size="sm"
                    onClick={() => {
                      setEditingBoard(editingBoard === cred.board ? null : cred.board);
                      setCredUsername("");
                      setCredPassword("");
                    }}
                  >
                    {cred.has_credentials ? "Update" : "Connect"}
                  </Button>
                </div>
              </div>
              <CardDescription>
                {info?.description || "Save your credentials for this job board."}
              </CardDescription>
            </CardHeader>

            {editingBoard === cred.board && (
              <CardContent className="space-y-3 pt-0">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">
                    {info?.usernameLabel || "Email"}
                  </label>
                  <input
                    type="email"
                    value={credUsername}
                    onChange={(e) => setCredUsername(e.target.value)}
                    placeholder={info?.usernamePlaceholder || "your.email@example.com"}
                    className="w-full rounded-md border px-3 py-2 text-sm bg-background"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">
                    Password
                  </label>
                  <input
                    type="password"
                    value={credPassword}
                    onChange={(e) => setCredPassword(e.target.value)}
                    placeholder="Your password"
                    className="w-full rounded-md border px-3 py-2 text-sm bg-background"
                  />
                </div>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    onClick={() => handleSaveCredential(cred.board)}
                    disabled={savingCred || !credUsername.trim() || !credPassword.trim()}
                  >
                    {savingCred ? "Saving..." : "Save Credentials"}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setEditingBoard(null);
                      setCredUsername("");
                      setCredPassword("");
                    }}
                  >
                    Cancel
                  </Button>
                </div>
              </CardContent>
            )}
          </Card>
        );
      })}

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

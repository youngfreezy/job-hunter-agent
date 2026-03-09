// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { signIn } from "next-auth/react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { API_BASE, getAuthHeaders } from "@/lib/api";

interface UserInfo {
  id: string;
  email: string;
  name: string | null;
  wallet_balance: number;
  free_applications_remaining: number;
  is_premium: boolean;
  auth_provider: string;
  created_at: string | null;
}

function providerLabel(provider: string) {
  if (provider === "both") return "Google + Email";
  if (provider === "google") return "Google";
  return "Email";
}

function formatDate(iso: string | null) {
  if (!iso) return "Unknown";
  return new Date(iso).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export default function AccountPage() {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    async function fetchUser() {
      try {
        const auth = await getAuthHeaders();
        const res = await fetch(`${API_BASE}/api/auth/me`, { headers: auth });
        if (res.ok) {
          const data = await res.json();
          setUser(data.user);
        }
      } catch {} 
    }
    fetchUser();
  }, []);

  async function handleDeleteAccount() {
    if (!confirm("This will permanently delete all your data. This cannot be undone. Are you sure?")) return;
    if (!confirm("Last chance — all sessions, applications, and billing data will be erased forever.")) return;
    setDeleting(true);
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_BASE}/api/auth/me/data`, {
        method: "DELETE",
        headers: auth,
      });
      if (res.ok) {
        window.location.href = "/api/auth/signout";
      } else {
        alert("Failed to delete account. Please try again or contact support.");
        setDeleting(false);
      }
    } catch {
      alert("Failed to delete account. Please try again.");
      setDeleting(false);
    }
  }

  if (loading) {
    return (
      <div className="container mx-auto max-w-4xl p-6 space-y-6">
        <div className="h-8 w-48 bg-muted animate-pulse rounded" />
        <div className="grid gap-4 mt-4">
          <div className="h-48 bg-muted animate-pulse rounded-lg" />
          <div className="h-32 bg-muted animate-pulse rounded-lg" />
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="container mx-auto max-w-4xl p-6">
        <p className="text-muted-foreground">Unable to load account information.</p>
      </div>
    );
  }

  return (
    <div className="container mx-auto max-w-4xl p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">My Account</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Manage your profile and account settings
        </p>
      </div>

      {/* Profile Info */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Profile</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-wide">Name</p>
              <p className="font-medium">{user.name || "Not set"}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-wide">Email</p>
              <p className="font-medium">{user.email}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-wide">Sign-in Method</p>
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-full bg-muted">
                  {providerLabel(user.auth_provider)}
                </span>
                {user.auth_provider === "email" && (
                  <button
                    onClick={() => signIn("google", { callbackUrl: "/account" })}
                    className="text-xs text-primary hover:underline"
                  >
                    Connect Google
                  </button>
                )}
              </div>
            </div>
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-wide">Member Since</p>
              <p className="font-medium">{formatDate(user.created_at)}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Subscription & Credits */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Subscription & Credits</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-3 gap-4">
            <div className="text-center p-4 bg-muted/50 rounded-lg">
              <p className="text-3xl font-bold">{user.wallet_balance.toFixed(0)}</p>
              <p className="text-xs text-muted-foreground mt-1">Credits</p>
            </div>
            <div className="text-center p-4 bg-muted/50 rounded-lg">
              <p className="text-3xl font-bold">{user.free_applications_remaining}</p>
              <p className="text-xs text-muted-foreground mt-1">Free Apps Left</p>
            </div>
            <div className="text-center p-4 bg-muted/50 rounded-lg">
              <p className="text-3xl font-bold">{user.is_premium ? "Active" : "Free"}</p>
              <p className="text-xs text-muted-foreground mt-1">Plan</p>
            </div>
          </div>
          <Link href="/billing">
            <Button variant="outline" className="w-full mt-2">
              Manage Billing & Purchase Credits
            </Button>
          </Link>
        </CardContent>
      </Card>

      {/* Quick Links */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Settings</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <Link
            href="/settings"
            className="flex items-center justify-between p-3 rounded-lg hover:bg-muted/50 transition-colors"
          >
            <span className="text-sm font-medium">Notification Preferences</span>
            <span className="text-muted-foreground text-sm">&rarr;</span>
          </Link>
          <Link
            href="/billing"
            className="flex items-center justify-between p-3 rounded-lg hover:bg-muted/50 transition-colors"
          >
            <span className="text-sm font-medium">Transaction History</span>
            <span className="text-muted-foreground text-sm">&rarr;</span>
          </Link>
        </CardContent>
      </Card>

      {/* Danger Zone */}
      <Card className="border-red-200 dark:border-red-900/50">
        <CardHeader>
          <CardTitle className="text-lg text-red-600 dark:text-red-400">Danger Zone</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground mb-3">
            Permanently delete your account and all associated data. This action cannot be undone.
          </p>
          <Button
            variant="destructive"
            size="sm"
            onClick={handleDeleteAccount}
            disabled={deleting}
          >
            {deleting ? "Deleting..." : "Delete Account"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

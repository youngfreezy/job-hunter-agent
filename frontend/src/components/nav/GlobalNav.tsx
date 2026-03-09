// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { signIn } from "next-auth/react";
import { Button } from "@/components/ui/button";
import { NavShell } from "./NavShell";
import { API_BASE, getAuthHeaders } from "@/lib/api";

const NAV_LINKS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/apply", label: "Review & Apply" },
  { href: "/interview-prep", label: "Interview Prep" },
  { href: "/career-pivot", label: "Career Change" },
  { href: "/freelance", label: "Freelance" },
  { href: "/autopilot", label: "Autopilot" },
  { href: "/history", label: "History" },
  { href: "/billing", label: "Billing" },
  { href: "/settings", label: "Settings" },
];

function handleSignOut() {
  // Clear persisted form data from localStorage
  for (let i = localStorage.length - 1; i >= 0; i--) {
    const key = localStorage.key(i);
    if (key?.startsWith("jh_")) localStorage.removeItem(key);
  }
  // Clear sessionStorage
  sessionStorage.clear();
  // Redirect to NextAuth sign-out
  window.location.href = "/api/auth/signout";
}

export function GlobalNav() {
  const pathname = usePathname();
  const [credits, setCredits] = useState<number | null>(null);
  const [showGoogleBanner, setShowGoogleBanner] = useState(false);

  useEffect(() => {
    async function fetchData() {
      try {
        const auth = await getAuthHeaders();
        const [walletRes, meRes] = await Promise.all([
          fetch(`${API_BASE}/api/billing/wallet`, { headers: auth }),
          fetch(`${API_BASE}/api/auth/me`, { headers: auth }),
        ]);
        if (walletRes.ok) {
          const data = await walletRes.json();
          setCredits(data.balance);
        }
        if (meRes.ok) {
          const data = await meRes.json();
          const provider = data.user?.auth_provider;
          if (provider === "email") {
            const dismissed = sessionStorage.getItem("jh_google_banner_dismissed");
            if (!dismissed) setShowGoogleBanner(true);
          }
        }
      } catch {}
    }
    fetchData();
  }, []);

  const creditsBg =
    credits === null
      ? ""
      : credits > 5
        ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400"
        : credits > 0
          ? "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400"
          : "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400";

  return (
    <>
    <NavShell>
      {/* Row 1: Branding + Actions */}
      <div className="flex items-center justify-between py-2.5">
        <Link
          href="/"
          className="text-lg font-bold bg-gradient-to-r from-blue-600 to-blue-700 bg-clip-text text-transparent"
        >
          JobHunter Agent
        </Link>
        <div className="flex items-center gap-3">
          {credits !== null && (
            <Link
              href="/billing"
              className={`px-2.5 py-0.5 text-xs font-semibold rounded-full ${creditsBg}`}
            >
              {credits.toFixed(0)} {credits === 1 ? "credit" : "credits"}
            </Link>
          )}
          <Link href="/session/new">
            <Button size="sm">New Session</Button>
          </Link>
          <button
            onClick={handleSignOut}
            className="text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            Sign Out
          </button>
        </div>
      </div>
      {/* Row 2: Page Links */}
      <div className="flex items-center gap-1 -mb-px">
        {NAV_LINKS.map(({ href, label }) => {
          const isActive = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={`px-3 py-2 text-xs font-medium transition-colors border-b-2 ${
                isActive
                  ? "border-primary text-foreground font-semibold"
                  : "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
              }`}
            >
              {label}
            </Link>
          );
        })}
      </div>
    </NavShell>
    {showGoogleBanner && (
      <div className="border-b border-blue-200 bg-blue-50 dark:border-blue-900 dark:bg-blue-950/30 px-4 py-2.5">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-3">
          <p className="text-xs text-blue-800 dark:text-blue-300">
            <span className="font-semibold">Connect Google</span> to auto-enter verification codes from job sites during applications.
          </p>
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={() => signIn("google", { callbackUrl: window.location.href })}
              className="rounded-md bg-blue-600 px-3 py-1 text-xs font-medium text-white hover:bg-blue-700"
            >
              Connect Google
            </button>
            <button
              onClick={() => {
                setShowGoogleBanner(false);
                sessionStorage.setItem("jh_google_banner_dismissed", "1");
              }}
              className="text-blue-400 hover:text-blue-600 dark:text-blue-500 dark:hover:text-blue-300"
              aria-label="Dismiss"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    )}
    </>
  );
}

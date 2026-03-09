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

  const creditColor =
    credits === null
      ? "text-muted-foreground"
      : credits > 5
        ? "text-emerald-600"
        : credits > 0
          ? "text-amber-500"
          : "text-red-500";

  return (
    <>
    <NavShell>
      <div className="flex items-center gap-3">
        {NAV_LINKS.map(({ href, label }) => {
          const isActive = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                isActive
                  ? "bg-muted text-foreground"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
              }`}
            >
              {label}
            </Link>
          );
        })}
        {credits !== null && (
          <Link
            href="/billing"
            className={`px-2.5 py-1 text-xs font-bold rounded-full border ${creditColor} ${
              credits <= 5 ? "border-current animate-pulse" : "border-transparent bg-muted/50"
            }`}
          >
            {credits.toFixed(0)} cr
          </Link>
        )}
        <Link href="/session/new">
          <Button size="sm">New Session</Button>
        </Link>
        <button
          onClick={handleSignOut}
          className="px-3 py-1.5 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
        >
          Sign Out
        </button>
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

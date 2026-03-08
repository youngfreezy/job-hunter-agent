// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
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

  useEffect(() => {
    async function fetchCredits() {
      try {
        const auth = await getAuthHeaders();
        const res = await fetch(`${API_BASE}/api/billing/wallet`, { headers: auth });
        if (res.ok) {
          const data = await res.json();
          setCredits(data.balance);
        }
      } catch {}
    }
    fetchCredits();
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
  );
}

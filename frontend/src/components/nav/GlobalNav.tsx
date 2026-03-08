"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Button } from "@/components/ui/button";
import { NavShell } from "./NavShell";

const NAV_LINKS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/apply", label: "Review & Apply" },
  { href: "/interview-prep", label: "Interview Prep" },
  { href: "/career-pivot", label: "Career Change" },
  { href: "/freelance", label: "Freelance" },
  { href: "/history", label: "History" },
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

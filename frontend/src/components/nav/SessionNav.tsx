// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Button } from "@/components/ui/button";
import { NavShell } from "./NavShell";

export function SessionNav({ sessionId }: { sessionId: string }) {
  const pathname = usePathname();

  const tabs = [
    { href: `/session/${sessionId}`, label: "Activity" },
    { href: `/session/${sessionId}/manual-apply`, label: "Review & Apply" },
    { href: `/session/${sessionId}/interview-prep`, label: "Interview Prep" },
    { href: `/session/${sessionId}/career-pivot`, label: "Career Change" },
    { href: `/session/${sessionId}/settings`, label: "Settings" },
  ];

  return (
    <NavShell>
      <div className="relative flex items-center justify-center py-2">
        <div className="hidden sm:flex items-center gap-1">
          {tabs.map(({ href, label }) => {
            const isActive = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                  isActive
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                }`}
              >
                {label}
              </Link>
            );
          })}
        </div>
        <Link href="/dashboard" className="absolute right-0">
          <Button variant="outline" size="sm">
            Dashboard
          </Button>
        </Link>
      </div>
    </NavShell>
  );
}

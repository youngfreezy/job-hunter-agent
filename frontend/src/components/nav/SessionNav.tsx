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
      <div className="flex items-center gap-2 py-2">
        <nav aria-label="Run views" className="-mx-1 min-w-0 flex-1 overflow-x-auto">
          <ul className="flex w-max items-center gap-1 px-1">
            {tabs.map(({ href, label }) => {
              const isActive = pathname === href;
              return (
                <li key={href}>
                  <Link
                    href={href}
                    aria-current={isActive ? "page" : undefined}
                    className={`inline-flex min-h-11 items-center whitespace-nowrap rounded-md px-3 text-sm font-medium transition-colors sm:min-h-9 ${
                      isActive
                        ? "bg-primary/10 text-primary"
                        : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                    }`}
                  >
                    {label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
        <Link href="/dashboard" className="shrink-0">
          <Button variant="outline" size="sm">
            Dashboard
          </Button>
        </Link>
      </div>
    </NavShell>
  );
}

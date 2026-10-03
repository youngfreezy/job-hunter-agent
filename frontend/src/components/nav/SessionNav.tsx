// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

/** Breadcrumb, run title and the run's tab row. Shared by every run route. */
export function SessionNav({ sessionId, name }: { sessionId: string; name: string | null }) {
  const pathname = usePathname();
  const base = `/session/${sessionId}`;
  const tabs = [
    { href: base, label: "Activity" },
    { href: `${base}/manual-apply`, label: "Applications" },
    { href: `${base}/settings`, label: "Parameters" },
  ];

  return (
    <div className="mb-5 flex flex-col gap-2">
      <nav aria-label="Breadcrumb" className="text-[13px] text-muted-foreground">
        <ol className="flex min-w-0 items-center gap-1.5">
          <li>
            <Link href="/dashboard" className="rounded hover:text-foreground">
              Home
            </Link>
          </li>
          <li aria-hidden="true">/</li>
          <li aria-current="page" className="truncate text-foreground">
            {name ?? "Run"}
          </li>
        </ol>
      </nav>
      <h1 className="min-h-8 text-2xl font-semibold tracking-tight text-foreground">
        {name ?? <span className="inline-block h-6 w-72 max-w-full rounded-md bg-muted" />}
      </h1>
      <nav aria-label="Run views" className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
        <ul className="flex min-w-max gap-5 border-b border-border">
          {tabs.map(({ href, label }) => {
            const active = pathname === href;
            return (
              <li key={href}>
                <Link
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "-mb-px inline-flex min-h-11 items-center border-b-2 text-sm font-medium transition-colors sm:min-h-10",
                    active
                      ? "border-primary text-foreground"
                      : "border-transparent text-muted-foreground hover:text-foreground"
                  )}
                >
                  {label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </div>
  );
}

// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import Link from "next/link";

export function NavShell({ children }: { children: React.ReactNode }) {
  return (
    <nav className="sticky top-0 z-50 border-b border-border/70 bg-background/95 px-6 py-3 shadow-sm supports-[backdrop-filter]:bg-background/90 supports-[backdrop-filter]:backdrop-blur-md">
      <div className="max-w-7xl mx-auto flex items-center justify-between">
        <Link
          href="/"
          className="text-lg font-bold bg-gradient-to-r from-blue-600 to-blue-700 bg-clip-text text-transparent"
        >
          JobHunter Agent
        </Link>
        {children}
      </div>
    </nav>
  );
}

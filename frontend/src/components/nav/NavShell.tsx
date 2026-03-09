// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

export function NavShell({ children }: { children: React.ReactNode }) {
  return (
    <nav className="sticky top-0 z-50 border-b border-border/70 bg-background/95 shadow-sm supports-[backdrop-filter]:bg-background/90 supports-[backdrop-filter]:backdrop-blur-md">
      <div className="max-w-7xl mx-auto px-6">
        {children}
      </div>
    </nav>
  );
}

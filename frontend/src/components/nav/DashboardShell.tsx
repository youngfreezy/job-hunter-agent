// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { usePathname } from "next/navigation";
import { GlobalNav } from "@/components/nav/GlobalNav";

export function DashboardShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isLanding = pathname === "/";

  if (isLanding) {
    return <>{children}</>;
  }

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <GlobalNav />
      <div className="flex-1">{children}</div>
    </div>
  );
}

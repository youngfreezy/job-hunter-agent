// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { usePathname } from "next/navigation";
import { AppShell } from "@/components/nav/AppShell";

export function DashboardShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  if (pathname === "/") return <>{children}</>;
  return <AppShell>{children}</AppShell>;
}

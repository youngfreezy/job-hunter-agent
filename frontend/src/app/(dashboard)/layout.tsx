// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { DashboardShell } from "@/components/nav/DashboardShell";

export default function DashboardGroupLayout({ children }: { children: React.ReactNode }) {
  return <DashboardShell>{children}</DashboardShell>;
}

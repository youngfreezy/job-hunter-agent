// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { SessionShell } from "@/components/nav/SessionShell";

export default function SessionGroupLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <SessionShell>{children}</SessionShell>;
}

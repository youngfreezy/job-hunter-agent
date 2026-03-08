// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useParams } from "next/navigation";
import { SessionNav } from "@/components/nav/SessionNav";

export function SessionShell({ children }: { children: React.ReactNode }) {
  const { id } = useParams<{ id: string }>();

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <SessionNav sessionId={id} />
      <div className="flex-1">{children}</div>
    </div>
  );
}

// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { AppShell } from "@/components/nav/AppShell";
import { SessionNav } from "@/components/nav/SessionNav";
import { getSession } from "@/lib/api";
import { runName } from "@/lib/run";

export function SessionShell({ children }: { children: React.ReactNode }) {
  const { id } = useParams<{ id: string }>();
  const [name, setName] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    getSession(id)
      .then((s) => {
        if (!live) return;
        const n = runName(s as { keywords?: string[]; locations?: string[]; remote_only?: boolean });
        setName(n);
        document.title = `${n} · JobHunter`;
      })
      .catch(() => live && setName("Run"));
    return () => {
      live = false;
    };
  }, [id]);

  return (
    <AppShell>
      <div className="mx-auto w-full max-w-[1120px] px-4 pb-24 pt-5 sm:px-6 lg:px-8 lg:pb-12">
        <SessionNav sessionId={id} name={name} />
        {children}
      </div>
    </AppShell>
  );
}

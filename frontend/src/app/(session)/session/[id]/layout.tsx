"use client";

import { useParams } from "next/navigation";
import { SessionNav } from "@/components/nav/SessionNav";

export default function SessionGroupLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { id } = useParams<{ id: string }>();

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <SessionNav sessionId={id} />
      <div className="flex-1">{children}</div>
    </div>
  );
}

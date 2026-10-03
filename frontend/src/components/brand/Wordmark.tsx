// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import Link from "next/link";
import { cn } from "@/lib/utils";

/** The mark is a pipeline line with two notches, one per approval gate. */
export function WordmarkMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" className={cn("h-5 w-5", className)}>
      <path
        d="M2 12h4l2-4 2 4h1l2-4 2 4h3"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function Wordmark({
  href = "/",
  size = "md",
  className,
}: {
  href?: string;
  size?: "sm" | "md";
  className?: string;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "inline-flex items-center gap-2 rounded-md font-semibold tracking-tight text-foreground",
        size === "md" ? "text-base" : "text-sm",
        className
      )}
    >
      <WordmarkMark className="text-primary" />
      <span>JobHunter</span>
    </Link>
  );
}

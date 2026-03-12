// Copyright (c) 2026 V2 Software LLC. All rights reserved.

export default function QuickApplyLoading() {
  return (
    <div className="max-w-3xl mx-auto px-6 py-12 space-y-6">
      {/* Header */}
      <div className="space-y-2">
        <div className="h-9 w-48 animate-pulse rounded-lg bg-zinc-200 dark:bg-zinc-800" />
        <div className="h-5 w-80 animate-pulse rounded bg-zinc-200 dark:bg-zinc-800" />
      </div>

      {/* Resume card */}
      <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 p-6">
        <div className="flex items-center justify-between">
          <div className="space-y-1.5">
            <div className="h-4 w-24 animate-pulse rounded bg-zinc-200 dark:bg-zinc-800" />
            <div className="h-3 w-40 animate-pulse rounded bg-zinc-200 dark:bg-zinc-800" />
          </div>
          <div className="h-8 w-28 animate-pulse rounded-md bg-zinc-200 dark:bg-zinc-800" />
        </div>
      </div>

      {/* URL textarea card */}
      <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 p-6 space-y-4">
        <div className="space-y-1.5">
          <div className="h-5 w-20 animate-pulse rounded bg-zinc-200 dark:bg-zinc-800" />
          <div className="h-3 w-64 animate-pulse rounded bg-zinc-200 dark:bg-zinc-800" />
        </div>
        <div className="h-44 w-full animate-pulse rounded-lg bg-zinc-200 dark:bg-zinc-800" />
      </div>

      {/* Button */}
      <div className="h-12 w-full animate-pulse rounded-lg bg-zinc-200 dark:bg-zinc-800" />
    </div>
  );
}

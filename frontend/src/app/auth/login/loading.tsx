// Copyright (c) 2026 V2 Software LLC. All rights reserved.

export default function Loading() {
  return (
    <div className="min-h-screen bg-white dark:bg-zinc-950 flex items-center justify-center px-4">
      <div className="w-full max-w-md rounded-lg border border-zinc-200 dark:border-zinc-800 p-6">
        <div className="text-center mb-6">
          <div className="h-7 w-40 mx-auto bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse mb-3" />
          <div className="h-5 w-52 mx-auto bg-zinc-100 dark:bg-zinc-900 rounded animate-pulse" />
        </div>
        <div className="space-y-3">
          <div className="h-10 w-full bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse" />
          <div className="h-4 w-full bg-zinc-100 dark:bg-zinc-900 rounded animate-pulse" />
          <div className="h-10 w-full bg-zinc-100 dark:bg-zinc-900 rounded animate-pulse" />
          <div className="h-10 w-full bg-zinc-100 dark:bg-zinc-900 rounded animate-pulse" />
          <div className="h-10 w-full bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse" />
        </div>
      </div>
    </div>
  );
}

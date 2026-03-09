// Copyright (c) 2026 V2 Software LLC. All rights reserved.

export default function Loading() {
  return (
    <div className="min-h-screen bg-white dark:bg-zinc-950">
      {/* Nav */}
      <nav className="border-b border-zinc-200 dark:border-zinc-800 px-6 py-4 flex items-center justify-between max-w-7xl mx-auto">
        <div className="h-6 w-40 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse" />
        <div className="h-9 w-36 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse" />
      </nav>

      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Title */}
        <div className="h-8 w-32 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse mb-6" />

        {/* Stats row */}
        <div className="grid grid-cols-4 gap-4 mb-8">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="rounded-lg border border-zinc-200 dark:border-zinc-800 p-4">
              <div className="h-3 w-24 bg-zinc-100 dark:bg-zinc-900 rounded animate-pulse mb-2" />
              <div className="h-7 w-12 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse" />
            </div>
          ))}
        </div>

        {/* Session list skeleton */}
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="rounded-lg border border-zinc-200 dark:border-zinc-800 p-4 flex items-center justify-between"
            >
              <div className="space-y-2">
                <div className="h-5 w-48 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse" />
                <div className="h-3 w-32 bg-zinc-100 dark:bg-zinc-900 rounded animate-pulse" />
              </div>
              <div className="h-6 w-20 bg-zinc-200 dark:bg-zinc-800 rounded-full animate-pulse" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

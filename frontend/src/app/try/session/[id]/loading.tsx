// Copyright (c) 2026 V2 Software LLC. All rights reserved.

export default function Loading() {
  return (
    <div className="min-h-screen bg-white dark:bg-zinc-950">
      <nav className="border-b border-zinc-200 dark:border-zinc-800 px-6 py-4">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div className="h-6 w-40 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse" />
          <div className="h-4 w-20 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse" />
        </div>
      </nav>
      <div className="max-w-4xl mx-auto px-6 py-10">
        <div className="h-8 w-64 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse mb-4" />
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-20 w-full bg-zinc-100 dark:bg-zinc-900 rounded-xl animate-pulse" />
          ))}
        </div>
      </div>
    </div>
  );
}

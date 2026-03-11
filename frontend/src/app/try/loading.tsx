// Copyright (c) 2026 V2 Software LLC. All rights reserved.

export default function Loading() {
  return (
    <div className="min-h-screen bg-white dark:bg-zinc-950">
      <nav className="border-b border-zinc-200 dark:border-zinc-800 px-6 py-4 flex items-center justify-between max-w-7xl mx-auto">
        <div className="h-6 w-40 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse" />
        <div className="h-4 w-20 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse" />
      </nav>

      <div className="max-w-2xl mx-auto px-6 py-12">
        <div className="h-8 w-64 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse mb-2" />
        <div className="h-5 w-96 bg-zinc-100 dark:bg-zinc-900 rounded animate-pulse mb-8" />

        <div className="flex items-center justify-between mb-8">
          {[1, 2, 3].map((i) => (
            <div key={i} className="flex items-center flex-1">
              <div className="w-8 h-8 rounded-full bg-zinc-200 dark:bg-zinc-800 animate-pulse" />
              {i < 3 && <div className="flex-1 h-0.5 bg-zinc-200 dark:bg-zinc-800 mx-2 animate-pulse" />}
            </div>
          ))}
        </div>

        <div className="space-y-4">
          <div className="h-5 w-32 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse" />
          <div className="h-10 w-full bg-zinc-200 dark:bg-zinc-800 rounded-lg animate-pulse" />
          <div className="h-5 w-24 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse" />
          <div className="h-10 w-full bg-zinc-200 dark:bg-zinc-800 rounded-lg animate-pulse" />
        </div>

        <div className="flex justify-end mt-8">
          <div className="h-10 w-28 bg-zinc-200 dark:bg-zinc-800 rounded-lg animate-pulse" />
        </div>
      </div>
    </div>
  );
}

// Copyright (c) 2026 V2 Software LLC. All rights reserved.

export default function HistoryLoading() {
  return (
    <div className="max-w-5xl mx-auto px-6 py-8 space-y-6">
      <div className="space-y-2">
        <div className="h-8 w-48 bg-zinc-200 dark:bg-zinc-700 rounded animate-pulse" />
        <div className="h-4 w-80 bg-zinc-200 dark:bg-zinc-700 rounded animate-pulse" />
      </div>
      <div className="h-36 bg-zinc-200 dark:bg-zinc-700 rounded-2xl animate-pulse" />
      <div className="space-y-3">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="h-24 bg-zinc-200 dark:bg-zinc-700 rounded-2xl animate-pulse" />
        ))}
      </div>
    </div>
  );
}

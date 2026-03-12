// Copyright (c) 2026 V2 Software LLC. All rights reserved.

export default function AboutLoading() {
  return (
    <div className="min-h-screen bg-white dark:bg-zinc-950">
      <nav className="border-b border-zinc-200 dark:border-zinc-800 px-6 py-4">
        <div className="mx-auto max-w-4xl">
          <div className="h-6 w-40 animate-pulse rounded bg-zinc-200 dark:bg-zinc-800" />
        </div>
      </nav>
      <main className="mx-auto max-w-4xl px-6 py-16 space-y-8">
        <div className="h-10 w-80 animate-pulse rounded bg-zinc-200 dark:bg-zinc-800" />
        <div className="h-5 w-full max-w-lg animate-pulse rounded bg-zinc-200 dark:bg-zinc-800" />
        <div className="space-y-6 pt-8">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="h-28 w-full animate-pulse rounded-xl bg-zinc-100 dark:bg-zinc-900"
            />
          ))}
        </div>
      </main>
    </div>
  );
}

// Copyright (c) 2026 V2 Software LLC. All rights reserved.

export default function AgentDetailLoading() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <div className="animate-pulse space-y-6">
        <div className="h-6 w-32 bg-muted rounded" />
        <div className="h-10 w-72 bg-muted rounded" />
        <div className="h-5 w-full bg-muted rounded" />
        <div className="h-5 w-3/4 bg-muted rounded" />
        <div className="flex gap-2">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-10 w-10 bg-muted rounded-full" />
          ))}
        </div>
        <div className="h-12 w-40 bg-muted rounded-lg" />
        <div className="h-px w-full bg-muted" />
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-24 w-full bg-muted rounded-lg" />
          ))}
        </div>
      </div>
    </main>
  );
}

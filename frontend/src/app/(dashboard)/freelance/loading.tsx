// Copyright (c) 2026 V2 Software LLC. All rights reserved.

export default function FreelanceLoading() {
  return (
    <div className="container mx-auto max-w-4xl p-6">
      <div className="h-8 w-64 bg-muted animate-pulse rounded mb-2" />
      <div className="h-4 w-96 bg-muted animate-pulse rounded mb-8" />

      <div className="bg-card border rounded-lg p-6 space-y-6">
        <div className="h-24 bg-muted animate-pulse rounded-lg" />

        <div className="space-y-2">
          <div className="h-4 w-32 bg-muted animate-pulse rounded" />
          <div className="flex items-center gap-3">
            <div className="h-9 w-20 bg-muted animate-pulse rounded" />
            <div className="h-4 w-4 bg-muted animate-pulse rounded" />
            <div className="h-9 w-20 bg-muted animate-pulse rounded" />
          </div>
        </div>

        <div className="space-y-2">
          <div className="h-4 w-36 bg-muted animate-pulse rounded" />
          <div className="flex gap-2">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-9 w-28 bg-muted animate-pulse rounded-md" />
            ))}
          </div>
        </div>

        <div className="space-y-2">
          <div className="h-4 w-24 bg-muted animate-pulse rounded" />
          <div className="flex gap-3">
            <div className="h-9 w-36 bg-muted animate-pulse rounded-md" />
            <div className="h-9 w-40 bg-muted animate-pulse rounded-md" />
          </div>
        </div>

        <div className="h-11 w-full bg-muted animate-pulse rounded-md" />
      </div>
    </div>
  );
}

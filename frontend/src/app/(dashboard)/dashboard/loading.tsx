// Copyright (c) 2026 V2 Software LLC. All rights reserved.

export default function Loading() {
  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      {/* Title */}
      <div className="h-8 w-32 bg-muted rounded animate-pulse mb-6" />

      {/* Stats row */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="rounded-lg border border-border p-4">
            <div className="h-3 w-24 bg-muted rounded animate-pulse mb-2" />
            <div className="h-7 w-12 bg-muted rounded animate-pulse" />
          </div>
        ))}
      </div>

      {/* Session list skeleton */}
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="rounded-lg border border-border p-4 flex items-center justify-between"
          >
            <div className="space-y-2">
              <div className="h-5 w-48 bg-muted rounded animate-pulse" />
              <div className="h-3 w-32 bg-muted/50 rounded animate-pulse" />
            </div>
            <div className="h-6 w-20 bg-muted rounded-full animate-pulse" />
          </div>
        ))}
      </div>
    </div>
  );
}

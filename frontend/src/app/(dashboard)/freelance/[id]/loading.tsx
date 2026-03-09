// Copyright (c) 2026 V2 Software LLC. All rights reserved.

export default function FreelanceResultLoading() {
  return (
    <div className="container mx-auto max-w-4xl p-6 space-y-8">
      {/* Page title */}
      <div className="h-8 w-40 bg-muted animate-pulse rounded" />

      {/* Status indicator */}
      <div className="bg-card border rounded-lg p-6 text-center space-y-3">
        <div className="h-8 w-8 bg-muted animate-pulse rounded-full mx-auto" />
        <div className="h-4 w-48 bg-muted animate-pulse rounded mx-auto" />
      </div>

      {/* Platform profiles skeleton */}
      <div className="bg-card border rounded-lg p-4 space-y-4">
        <div className="h-5 w-56 bg-muted animate-pulse rounded" />
        <div className="space-y-3">
          {[1, 2].map((i) => (
            <div key={i} className="border-l-2 border-muted pl-4 space-y-2">
              <div className="h-4 w-24 bg-muted animate-pulse rounded" />
              <div className="h-3 w-48 bg-muted animate-pulse rounded" />
              <div className="h-3 w-20 bg-muted animate-pulse rounded" />
              <div className="flex gap-1">
                {[1, 2, 3].map((j) => (
                  <div key={j} className="h-5 w-16 bg-muted animate-pulse rounded" />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Gig cards skeleton */}
      <div className="space-y-4">
        <div className="h-6 w-52 bg-muted animate-pulse rounded" />
        {[1, 2, 3].map((i) => (
          <div key={i} className="bg-card border rounded-lg p-5 space-y-3">
            <div className="flex items-start justify-between">
              <div className="space-y-2 flex-1">
                <div className="h-5 w-3/5 bg-muted animate-pulse rounded" />
                <div className="h-3 w-2/5 bg-muted animate-pulse rounded" />
              </div>
              <div className="h-5 w-20 bg-muted animate-pulse rounded" />
            </div>
            <div className="flex gap-4">
              <div className="h-4 w-24 bg-muted animate-pulse rounded" />
              <div className="h-4 w-20 bg-muted animate-pulse rounded" />
            </div>
            <div className="h-3 w-full bg-muted animate-pulse rounded" />
            <div className="h-3 w-4/5 bg-muted animate-pulse rounded" />
          </div>
        ))}
      </div>
    </div>
  );
}

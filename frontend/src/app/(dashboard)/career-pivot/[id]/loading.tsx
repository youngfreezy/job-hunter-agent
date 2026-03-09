// Copyright (c) 2026 V2 Software LLC. All rights reserved.

export default function PivotResultLoading() {
  return (
    <div className="container mx-auto max-w-4xl p-6 space-y-6">
      {/* Page title */}
      <div className="h-8 w-56 bg-muted animate-pulse rounded" />

      {/* Risk assessment skeleton */}
      <div className="bg-card border rounded-lg p-8 space-y-4">
        <div className="flex flex-col items-center space-y-3">
          <div className="h-4 w-44 bg-muted animate-pulse rounded" />
          <div className="h-16 w-24 bg-muted animate-pulse rounded" />
          <div className="h-3 w-28 bg-muted animate-pulse rounded" />
        </div>
        <div className="bg-muted/50 rounded-lg p-4 space-y-2">
          <div className="h-4 w-48 bg-muted animate-pulse rounded" />
          <div className="flex gap-4">
            <div className="h-3 w-32 bg-muted animate-pulse rounded" />
            <div className="h-3 w-24 bg-muted animate-pulse rounded" />
          </div>
        </div>
        {/* Task breakdown bars */}
        <div className="space-y-2 pt-2">
          <div className="h-4 w-52 bg-muted animate-pulse rounded" />
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="flex items-center gap-3">
              <div className="h-3 w-32 bg-muted animate-pulse rounded" />
              <div className="flex-1 h-4 bg-muted animate-pulse rounded-full" />
            </div>
          ))}
        </div>
      </div>

      {/* Pivot role cards skeleton */}
      {[1, 2, 3].map((i) => (
        <div key={i} className="bg-card border rounded-lg p-6 space-y-3">
          <div className="flex items-center justify-between">
            <div className="h-5 w-48 bg-muted animate-pulse rounded" />
            <div className="h-4 w-28 bg-muted animate-pulse rounded" />
          </div>
          <div className="w-full bg-muted rounded-full h-2">
            <div
              className="bg-muted animate-pulse h-2 rounded-full"
              style={{ width: `${40 + i * 15}%` }}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="h-4 w-32 bg-muted animate-pulse rounded" />
            <div className="h-4 w-28 bg-muted animate-pulse rounded" />
            <div className="h-4 w-36 bg-muted animate-pulse rounded" />
            <div className="h-4 w-24 bg-muted animate-pulse rounded" />
          </div>
        </div>
      ))}
    </div>
  );
}

// Copyright (c) 2026 V2 Software LLC. All rights reserved.

export default function InterviewPrepLoading() {
  return (
    <div className="container mx-auto max-w-3xl p-6 space-y-6">
      {/* Page title */}
      <div className="h-8 w-40 bg-muted animate-pulse rounded" />

      {/* Company Brief skeleton */}
      <div className="bg-card border rounded-lg p-4 space-y-3">
        <div className="h-5 w-32 bg-muted animate-pulse rounded" />
        <div className="space-y-2">
          <div className="flex gap-2">
            <div className="h-3 w-16 bg-muted animate-pulse rounded" />
            <div className="h-3 w-3/4 bg-muted animate-pulse rounded" />
          </div>
          <div className="flex gap-2">
            <div className="h-3 w-16 bg-muted animate-pulse rounded" />
            <div className="h-3 w-2/3 bg-muted animate-pulse rounded" />
          </div>
          <div className="flex gap-2">
            <div className="h-3 w-16 bg-muted animate-pulse rounded" />
            <div className="h-3 w-4/5 bg-muted animate-pulse rounded" />
          </div>
        </div>
      </div>

      {/* Question area skeleton */}
      <div className="bg-card border rounded-lg p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div className="h-4 w-20 bg-muted animate-pulse rounded" />
          <div className="h-4 w-24 bg-muted animate-pulse rounded" />
        </div>
        {/* Question text */}
        <div className="h-6 w-3/4 bg-muted animate-pulse rounded" />
        {/* Coaching button */}
        <div className="h-8 w-32 bg-muted animate-pulse rounded" />
        {/* Answer textarea */}
        <div className="h-28 w-full bg-muted animate-pulse rounded" />
        {/* Action buttons */}
        <div className="flex gap-3">
          <div className="h-9 w-28 bg-muted animate-pulse rounded" />
          <div className="h-9 w-16 bg-muted animate-pulse rounded" />
        </div>
      </div>
    </div>
  );
}

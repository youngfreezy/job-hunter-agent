// Copyright (c) 2026 V2 Software LLC. All rights reserved.

export default function InterviewPrepLoading() {
  return (
    <div className="container mx-auto max-w-3xl p-6 space-y-6">
      <div className="h-8 w-40 bg-muted animate-pulse rounded" />
      <div className="bg-card border rounded-lg p-6 space-y-3">
        <div className="h-5 w-32 bg-muted animate-pulse rounded" />
        <div className="space-y-2">
          <div className="h-3 w-full bg-muted animate-pulse rounded" />
          <div className="h-3 w-4/5 bg-muted animate-pulse rounded" />
          <div className="h-3 w-3/5 bg-muted animate-pulse rounded" />
        </div>
      </div>
      <div className="bg-card border rounded-lg p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div className="h-4 w-20 bg-muted animate-pulse rounded" />
          <div className="h-4 w-24 bg-muted animate-pulse rounded" />
        </div>
        <div className="h-5 w-3/4 bg-muted animate-pulse rounded" />
        <div className="h-28 w-full bg-muted animate-pulse rounded" />
      </div>
    </div>
  );
}

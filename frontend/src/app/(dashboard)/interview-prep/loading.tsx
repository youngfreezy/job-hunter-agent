// Copyright (c) 2026 V2 Software LLC. All rights reserved.

export default function InterviewPrepLoading() {
  return (
    <div className="container mx-auto max-w-4xl p-6 space-y-6">
      <div className="h-8 w-48 bg-muted animate-pulse rounded" />
      <div className="h-4 w-96 bg-muted animate-pulse rounded" />
      <div className="bg-card border rounded-lg p-8 space-y-6">
        <div className="flex flex-col items-center gap-3">
          <div className="h-16 w-16 bg-muted animate-pulse rounded-full" />
          <div className="h-6 w-64 bg-muted animate-pulse rounded" />
          <div className="h-4 w-80 bg-muted animate-pulse rounded" />
        </div>
        <div className="max-w-lg mx-auto space-y-4">
          <div className="h-24 bg-muted animate-pulse rounded-lg" />
          <div className="h-10 bg-muted animate-pulse rounded" />
          <div className="h-10 bg-muted animate-pulse rounded" />
        </div>
        <div className="flex justify-center">
          <div className="h-11 w-48 bg-muted animate-pulse rounded" />
        </div>
      </div>
    </div>
  );
}

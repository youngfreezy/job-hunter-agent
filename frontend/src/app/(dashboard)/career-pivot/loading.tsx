// Copyright (c) 2026 V2 Software LLC. All rights reserved.

export default function CareerPivotLoading() {
  return (
    <div className="container mx-auto max-w-4xl px-4 py-6 sm:p-6 space-y-6">
      <div className="h-8 w-64 bg-muted animate-pulse rounded" />
      <div className="h-4 w-96 bg-muted animate-pulse rounded" />
      <div className="grid gap-4 mt-8">
        <div className="h-48 bg-muted animate-pulse rounded-lg" />
        <div className="h-32 bg-muted animate-pulse rounded-lg" />
        <div className="h-32 bg-muted animate-pulse rounded-lg" />
      </div>
    </div>
  );
}

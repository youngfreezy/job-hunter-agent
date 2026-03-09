// Copyright (c) 2026 V2 Software LLC. All rights reserved.

export default function SettingsLoading() {
  return (
    <div className="container mx-auto max-w-2xl p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <div className="h-7 w-48 bg-muted animate-pulse rounded" />
          <div className="h-4 w-72 bg-muted animate-pulse rounded" />
        </div>
        <div className="h-9 w-28 bg-muted animate-pulse rounded" />
      </div>
      {[...Array(4)].map((_, i) => (
        <div
          key={i}
          className="rounded-lg border bg-card p-6 space-y-4 animate-pulse"
        >
          <div className="h-5 w-40 bg-muted rounded" />
          <div className="h-8 w-full bg-muted rounded" />
          <div className="h-4 w-56 bg-muted rounded" />
        </div>
      ))}
    </div>
  );
}

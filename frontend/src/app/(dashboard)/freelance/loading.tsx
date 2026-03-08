// Copyright (c) 2026 V2 Software LLC. All rights reserved.

export default function FreelanceLoading() {
  return (
    <div className="container mx-auto max-w-4xl p-6 space-y-6">
      <div className="h-8 w-48 bg-muted animate-pulse rounded" />
      <div className="h-4 w-80 bg-muted animate-pulse rounded" />
      <div className="grid grid-cols-2 gap-4 mt-6">
        <div className="h-12 bg-muted animate-pulse rounded" />
        <div className="h-12 bg-muted animate-pulse rounded" />
      </div>
      <div className="space-y-4 mt-8">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-32 bg-muted animate-pulse rounded-lg" />
        ))}
      </div>
    </div>
  );
}

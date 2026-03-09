// Copyright (c) 2026 V2 Software LLC. All rights reserved.

export default function Loading() {
  return (
    <div className="max-w-2xl mx-auto px-6 py-12">
      {/* Title */}
      <div className="h-8 w-48 bg-muted rounded animate-pulse mb-2" />
      <div className="h-5 w-96 bg-muted/50 rounded animate-pulse mb-8" />

      {/* Stepper skeleton */}
      <div className="flex items-center justify-between mb-8">
        {[1, 2, 3].map((i) => (
          <div key={i} className="flex items-center flex-1">
            <div className="flex flex-col items-center">
              <div className="w-10 h-10 rounded-full bg-muted animate-pulse" />
              <div className="h-3 w-16 bg-muted/50 rounded animate-pulse mt-2" />
            </div>
            {i < 3 && <div className="flex-1 h-0.5 mx-4 bg-muted" />}
          </div>
        ))}
      </div>

      {/* Card skeletons */}
      {[1, 2].map((i) => (
        <div key={i} className="rounded-lg border border-border p-6 mb-6">
          <div className="h-5 w-36 bg-muted rounded animate-pulse mb-4" />
          <div className="h-10 w-full bg-muted/50 rounded animate-pulse mb-3" />
          <div className="h-3 w-64 bg-muted/50 rounded animate-pulse" />
        </div>
      ))}

      {/* Button row skeleton */}
      <div className="flex justify-between mt-8">
        <div className="h-10 w-20 bg-muted rounded animate-pulse" />
        <div className="h-10 w-20 bg-muted rounded animate-pulse" />
      </div>
    </div>
  );
}

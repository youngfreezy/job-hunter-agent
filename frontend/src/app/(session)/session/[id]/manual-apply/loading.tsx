// Copyright (c) 2026 V2 Software LLC. All rights reserved.

export default function ManualApplyLoading() {
  return (
    <div className="max-w-5xl mx-auto px-6 py-8 space-y-4">
      <div className="h-8 w-64 bg-muted rounded-lg animate-pulse" />
      <div className="h-4 w-96 bg-muted rounded animate-pulse" />
      <div className="space-y-3 mt-6">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-40 bg-muted rounded-xl animate-pulse" />
        ))}
      </div>
    </div>
  );
}

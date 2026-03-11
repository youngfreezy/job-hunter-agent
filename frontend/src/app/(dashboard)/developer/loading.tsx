// Copyright (c) 2026 V2 Software LLC. All rights reserved.

export default function DeveloperLoading() {
  return (
    <main className="mx-auto max-w-4xl px-4 py-10">
      <div className="animate-pulse space-y-6">
        <div className="h-8 w-52 bg-muted rounded" />
        <div className="h-5 w-80 bg-muted rounded" />
        <div className="flex gap-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-9 w-24 bg-muted rounded-lg" />
          ))}
        </div>
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-20 w-full bg-muted rounded-lg" />
          ))}
        </div>
      </div>
    </main>
  );
}

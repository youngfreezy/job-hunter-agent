// Copyright (c) 2026 V2 Software LLC. All rights reserved.

export default function AutopilotLoading() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <div className="animate-pulse space-y-6">
        <div className="h-8 w-48 bg-muted rounded" />
        <div className="h-5 w-80 bg-muted rounded" />
        <div className="space-y-4">
          {[1, 2].map((i) => (
            <div key={i} className="h-36 w-full bg-muted rounded-xl" />
          ))}
        </div>
        <div className="h-10 w-40 bg-muted rounded-lg" />
      </div>
    </main>
  );
}

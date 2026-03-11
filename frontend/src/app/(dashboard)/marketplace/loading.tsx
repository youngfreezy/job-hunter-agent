// Copyright (c) 2026 V2 Software LLC. All rights reserved.

export default function MarketplaceLoading() {
  return (
    <main className="mx-auto max-w-5xl px-4 py-10">
      <div className="animate-pulse space-y-6">
        <div className="h-8 w-56 bg-muted rounded" />
        <div className="h-5 w-96 bg-muted rounded" />
        <div className="flex gap-2">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-8 w-20 bg-muted rounded-full" />
          ))}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-52 w-full bg-muted rounded-xl" />
          ))}
        </div>
      </div>
    </main>
  );
}

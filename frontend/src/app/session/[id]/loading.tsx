export default function Loading() {
  return (
    <div className="min-h-screen bg-background">
      {/* Nav */}
      <nav className="sticky top-0 z-50 backdrop-blur-xl bg-background/80 border-b border-border/50 px-6 py-3">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="h-6 w-40 bg-muted rounded-lg animate-pulse" />
          <div className="hidden sm:flex items-center gap-1">
            <div className="h-8 w-20 bg-muted rounded-md animate-pulse" />
            <div className="h-8 w-24 bg-muted rounded-md animate-pulse" />
            <div className="h-8 w-20 bg-muted rounded-md animate-pulse" />
          </div>
          <div className="h-8 w-24 bg-muted rounded-md animate-pulse" />
        </div>
      </nav>

      <div className="max-w-7xl mx-auto px-6 py-8 flex gap-6">
        {/* Main content area */}
        <div className="flex-1">
          {/* Pipeline progress skeleton */}
          <div className="flex items-center gap-3 mb-6">
            {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((i) => (
              <div key={i} className="flex items-center flex-1">
                <div className="w-8 h-8 rounded-full bg-muted animate-pulse" />
                {i < 10 && (
                  <div className="flex-1 h-0.5 mx-2 bg-muted" />
                )}
              </div>
            ))}
          </div>

          {/* Tab bar skeleton */}
          <div className="flex gap-4 border-b border-border mb-6">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="h-4 w-28 bg-muted rounded animate-pulse mb-3"
              />
            ))}
          </div>

          {/* Feed skeleton */}
          <div className="space-y-3">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="flex gap-3 items-start">
                <div className="h-4 w-16 bg-muted/50 rounded animate-pulse" />
                <div className="h-5 w-20 bg-muted rounded-full animate-pulse" />
                <div className="h-4 flex-1 bg-muted/50 rounded animate-pulse" />
              </div>
            ))}
          </div>
        </div>

        {/* Sidebar skeleton */}
        <div className="w-72 shrink-0">
          <div className="rounded-xl border border-border p-4 space-y-4">
            <div className="h-5 w-24 bg-muted rounded animate-pulse" />
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i}>
                  <div className="h-3 w-16 bg-muted/50 rounded animate-pulse mb-1" />
                  <div className="h-4 w-40 bg-muted rounded animate-pulse" />
                </div>
              ))}
            </div>
            {/* Stats pills skeleton */}
            <div className="grid grid-cols-2 gap-2">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="h-16 bg-muted rounded-lg animate-pulse" />
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

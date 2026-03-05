export default function Loading() {
  return (
    <div className="min-h-screen bg-white dark:bg-zinc-950">
      {/* Nav */}
      <nav className="border-b border-zinc-200 dark:border-zinc-800 px-6 py-4 flex items-center justify-between max-w-7xl mx-auto">
        <div className="h-6 w-40 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse" />
        <div className="flex gap-4">
          <div className="h-4 w-20 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse" />
          <div className="h-6 w-24 bg-zinc-200 dark:bg-zinc-800 rounded-full animate-pulse" />
        </div>
      </nav>

      <div className="max-w-7xl mx-auto px-6 py-8 flex gap-6">
        {/* Main content area */}
        <div className="flex-1">
          {/* Pipeline progress skeleton */}
          <div className="flex items-center gap-3 mb-6">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="flex items-center flex-1">
                <div className="w-8 h-8 rounded-full bg-zinc-200 dark:bg-zinc-800 animate-pulse" />
                {i < 5 && <div className="flex-1 h-0.5 mx-2 bg-zinc-200 dark:bg-zinc-800" />}
              </div>
            ))}
          </div>

          {/* Tab bar skeleton */}
          <div className="flex gap-4 border-b border-zinc-200 dark:border-zinc-800 mb-6">
            {["Status Feed", "Screenshot Feed", "Take Control"].map((_, i) => (
              <div key={i} className="h-4 w-28 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse mb-3" />
            ))}
          </div>

          {/* Feed skeleton */}
          <div className="space-y-3">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="flex gap-3 items-start">
                <div className="h-4 w-16 bg-zinc-100 dark:bg-zinc-900 rounded animate-pulse" />
                <div className="h-5 w-20 bg-zinc-200 dark:bg-zinc-800 rounded-full animate-pulse" />
                <div className="h-4 flex-1 bg-zinc-100 dark:bg-zinc-900 rounded animate-pulse" />
              </div>
            ))}
          </div>
        </div>

        {/* Sidebar skeleton */}
        <div className="w-72 shrink-0">
          <div className="rounded-lg border border-zinc-200 dark:border-zinc-800 p-4 space-y-4">
            <div className="h-5 w-24 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse" />
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i}>
                  <div className="h-3 w-16 bg-zinc-100 dark:bg-zinc-900 rounded animate-pulse mb-1" />
                  <div className="h-4 w-40 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse" />
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

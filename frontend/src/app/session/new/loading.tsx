export default function Loading() {
  return (
    <div className="min-h-screen bg-white dark:bg-zinc-950">
      {/* Nav */}
      <nav className="border-b border-zinc-200 dark:border-zinc-800 px-6 py-4 flex items-center justify-between max-w-7xl mx-auto">
        <div className="h-6 w-40 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse" />
        <div className="h-4 w-20 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse" />
      </nav>

      <div className="max-w-2xl mx-auto px-6 py-12">
        {/* Title */}
        <div className="h-8 w-48 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse mb-2" />
        <div className="h-5 w-96 bg-zinc-100 dark:bg-zinc-900 rounded animate-pulse mb-8" />

        {/* Stepper skeleton */}
        <div className="flex items-center justify-between mb-8">
          {[1, 2, 3].map((i) => (
            <div key={i} className="flex items-center flex-1">
              <div className="flex flex-col items-center">
                <div className="w-10 h-10 rounded-full bg-zinc-200 dark:bg-zinc-800 animate-pulse" />
                <div className="h-3 w-16 bg-zinc-100 dark:bg-zinc-900 rounded animate-pulse mt-2" />
              </div>
              {i < 3 && <div className="flex-1 h-0.5 mx-4 bg-zinc-200 dark:bg-zinc-800" />}
            </div>
          ))}
        </div>

        {/* Card skeletons */}
        {[1, 2].map((i) => (
          <div
            key={i}
            className="rounded-lg border border-zinc-200 dark:border-zinc-800 p-6 mb-6"
          >
            <div className="h-5 w-36 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse mb-4" />
            <div className="h-10 w-full bg-zinc-100 dark:bg-zinc-900 rounded animate-pulse mb-3" />
            <div className="h-3 w-64 bg-zinc-100 dark:bg-zinc-900 rounded animate-pulse" />
          </div>
        ))}

        {/* Button row skeleton */}
        <div className="flex justify-between mt-8">
          <div className="h-10 w-20 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse" />
          <div className="h-10 w-20 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse" />
        </div>
      </div>
    </div>
  );
}

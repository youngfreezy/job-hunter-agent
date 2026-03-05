export default function Loading() {
  return (
    <div className="min-h-screen bg-white dark:bg-zinc-950">
      {/* Nav skeleton */}
      <nav className="border-b border-zinc-200 dark:border-zinc-800 px-6 py-4 max-w-7xl mx-auto flex items-center justify-between">
        <div className="h-6 w-40 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse" />
        <div className="flex gap-4">
          <div className="h-4 w-20 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse" />
          <div className="h-4 w-24 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse" />
        </div>
      </nav>

      {/* Hero skeleton */}
      <div className="max-w-4xl mx-auto px-6 py-24 text-center">
        <div className="h-12 w-96 mx-auto bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse mb-4" />
        <div className="h-6 w-80 mx-auto bg-zinc-100 dark:bg-zinc-900 rounded animate-pulse mb-8" />
        <div className="h-12 w-48 mx-auto bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse" />
      </div>
    </div>
  );
}

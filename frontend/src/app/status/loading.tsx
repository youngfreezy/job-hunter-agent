export default function StatusLoading() {
  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950">
      <nav className="border-b border-zinc-200/80 px-6 py-4 dark:border-zinc-800">
        <div className="mx-auto flex max-w-4xl items-center justify-between">
          <div className="h-6 w-40 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse" />
          <div className="h-8 w-24 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse" />
        </div>
      </nav>
      <div className="mx-auto max-w-4xl px-6 py-16">
        <div className="h-8 w-48 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse mb-2" />
        <div className="h-4 w-80 bg-zinc-100 dark:bg-zinc-900 rounded animate-pulse mb-10" />
        <div className="h-24 bg-zinc-200 dark:bg-zinc-800 rounded-2xl animate-pulse mb-8" />
        <div className="space-y-3">
          <div className="h-16 bg-zinc-200 dark:bg-zinc-800 rounded-xl animate-pulse" />
          <div className="h-16 bg-zinc-200 dark:bg-zinc-800 rounded-xl animate-pulse" />
          <div className="h-16 bg-zinc-200 dark:bg-zinc-800 rounded-xl animate-pulse" />
        </div>
      </div>
    </div>
  );
}

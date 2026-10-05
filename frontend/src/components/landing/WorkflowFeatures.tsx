// Copyright (c) 2026 V2 Software LLC. All rights reserved.



export function WorkflowFeatures() {
  return (<>
    {/* Workflow features */}
    <section className="px-6 pb-10">
      <div className="mx-auto max-w-4xl">
        <div className="rounded-2xl border border-blue-200/60 bg-blue-50/50 px-6 py-5 dark:border-blue-900/40 dark:bg-blue-950/20">
          <div className="grid gap-4 sm:grid-cols-4 text-center">
            <div>
              <p className="text-2xl font-bold text-zinc-900 dark:text-white">Coach</p>
              <p className="text-xs text-zinc-500 dark:text-zinc-400">
                Resume feedback
              </p>
            </div>
            <div>
              <p className="text-2xl font-bold text-zinc-900 dark:text-white">Review</p>
              <p className="text-xs text-zinc-500 dark:text-zinc-400">Shortlist approval</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-emerald-600">Watch</p>
              <p className="text-xs text-zinc-500 dark:text-zinc-400">Browserbase Live View</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-zinc-900 dark:text-white">Track</p>
              <p className="text-xs text-zinc-500 dark:text-zinc-400">Application outcomes</p>
            </div>
          </div>
        </div>
      </div>
    </section>

  </>);
}

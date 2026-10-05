// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { Card, CardContent } from "@/components/ui/card";


export function TermsSection() {
  return (<>
    {/* Compliance & TOS */}
    <section className="px-6 pb-20">
      <div className="mx-auto max-w-4xl">
        <Card className="rounded-[28px] border-zinc-200/80 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950">
          <CardContent className="py-8 px-8">
            <h3 className="mb-4 text-center text-lg font-semibold">
              How we handle job board compliance
            </h3>
            <div className="grid gap-6 md:grid-cols-2">
              <div className="space-y-3 text-sm text-zinc-600 dark:text-zinc-400">
                <div className="flex items-start gap-2">
                  <span className="mt-0.5 text-emerald-600 shrink-0">&#10003;</span>
                  <span>
                    <strong className="text-zinc-900 dark:text-white">
                      Real accounts, real applications.
                    </strong>{" "}
                    Applications use your signed-in account and the resume and facts you provide.
                  </span>
                </div>
                <div className="flex items-start gap-2">
                  <span className="mt-0.5 text-emerald-600 shrink-0">&#10003;</span>
                  <span>
                    <strong className="text-zinc-900 dark:text-white">Human-in-the-loop.</strong>{" "}
                    Search runs include resume and shortlist review. Quick Apply uses the job links
                    you explicitly select; missing facts are queued for your answer.
                  </span>
                </div>
              </div>
              <div className="space-y-3 text-sm text-zinc-600 dark:text-zinc-400">
                <div className="flex items-start gap-2">
                  <span className="mt-0.5 text-emerald-600 shrink-0">&#10003;</span>
                  <span>
                    <strong className="text-zinc-900 dark:text-white">
                      Rate-limited and respectful.
                    </strong>{" "}
                    Applications run sequentially. Platform limits and account restrictions can still
                    interrupt a run.
                  </span>
                </div>
                <div className="flex items-start gap-2">
                  <span className="mt-0.5 text-emerald-600 shrink-0">&#10003;</span>
                  <span>
                    <strong className="text-zinc-900 dark:text-white">No data selling.</strong>{" "}
                    Resume and application content is processed by the selected AI provider and
                    Browserbase, and submitted to the selected job board and employer. We do not sell it.
                  </span>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </section>

  </>);
}

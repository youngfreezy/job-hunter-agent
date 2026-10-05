// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import { steps } from "./content";

export function HowItWorks() {
  return (<>
    {/* How It Works */}
    <section id="how-it-works" className="px-6 py-20 bg-white dark:bg-zinc-900/50">
      <div className="mx-auto max-w-6xl">
        <div className="mb-12 text-center">
          <h2 className="text-3xl font-bold">How It Works</h2>
          <p className="mt-2 text-zinc-600 dark:text-zinc-400">
            Four steps from setup to submitted applications. You control every stage.
          </p>
        </div>
        <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
          {steps.map((step) => (
            <Card
              key={step.num}
              className="rounded-3xl border-zinc-200/80 bg-zinc-50 shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
            >
              <CardHeader>
                <div className="mb-2 flex h-9 w-9 items-center justify-center rounded-full bg-zinc-900 text-sm font-bold text-white dark:bg-white dark:text-zinc-900">
                  {step.num}
                </div>
                <CardTitle className="text-lg">{step.title}</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm leading-6 text-zinc-600 dark:text-zinc-400">{step.desc}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </section>

  </>);
}

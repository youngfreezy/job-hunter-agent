// Copyright (c) 2026 V2 Software LLC. All rights reserved.


import { ROICalculator } from "./ROICalculator";

export function SearchCostSection() {
  return (<>
    {/* ROI Calculator */}
    <section className="px-6 py-20 bg-white dark:bg-zinc-900/50">
      <div className="mx-auto max-w-4xl">
        <h2 className="mb-4 text-center text-3xl font-bold">
          Estimate time and cost for your search
        </h2>
        <p className="mb-10 text-center text-zinc-600 dark:text-zinc-400">
          Explore an illustrative estimate using your own inputs. These figures are assumptions, not measured customer results, and exclude AI-provider and Browserbase fees.
        </p>
        <ROICalculator />
      </div>
    </section>

  </>);
}

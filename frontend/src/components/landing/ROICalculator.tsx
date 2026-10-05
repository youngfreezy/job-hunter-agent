// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useState } from "react";

import { estimateSearchCost } from "./cost-estimate";

export function ROICalculator() {
  const [appsPerWeek, setAppsPerWeek] = useState(20);
  const [hoursPerApp, setHoursPerApp] = useState(0.5);
  const [hourlyRate, setHourlyRate] = useState(50);

  const { weeklyHoursSaved, weeklyCostManual, creditCost, savings, roi } = estimateSearchCost(appsPerWeek, hoursPerApp, hourlyRate);

  return (
    <div className="grid gap-8 md:grid-cols-2">
      <div className="space-y-6">
        <div>
          <label className="mb-2 flex items-center justify-between text-sm font-medium text-zinc-700 dark:text-zinc-300">
            <span>Applications per week</span>
            <span className="text-zinc-900 dark:text-white font-bold">{appsPerWeek}</span>
          </label>
          <input
            type="range"
            min={5}
            max={100}
            value={appsPerWeek}
            onChange={(e) => setAppsPerWeek(Number(e.target.value))}
            className="w-full accent-blue-600"
          />
        </div>
        <div>
          <label className="mb-2 flex items-center justify-between text-sm font-medium text-zinc-700 dark:text-zinc-300">
            <span>Hours per manual application</span>
            <span className="text-zinc-900 dark:text-white font-bold">{hoursPerApp}h</span>
          </label>
          <input
            type="range"
            min={0.25}
            max={2}
            step={0.25}
            value={hoursPerApp}
            onChange={(e) => setHoursPerApp(Number(e.target.value))}
            className="w-full accent-blue-600"
          />
        </div>
        <div>
          <label className="mb-2 flex items-center justify-between text-sm font-medium text-zinc-700 dark:text-zinc-300">
            <span>Your hourly rate (or value of time)</span>
            <span className="text-zinc-900 dark:text-white font-bold">${hourlyRate}/hr</span>
          </label>
          <input
            type="range"
            min={15}
            max={150}
            step={5}
            value={hourlyRate}
            onChange={(e) => setHourlyRate(Number(e.target.value))}
            className="w-full accent-blue-600"
          />
        </div>
      </div>
      <div className="flex flex-col items-center justify-center rounded-2xl border border-emerald-200 bg-emerald-50/50 p-6 dark:border-emerald-900 dark:bg-emerald-950/20">
        <p className="text-sm text-zinc-600 dark:text-zinc-400">Manual time estimate</p>
        <p className="text-3xl font-bold text-zinc-900 dark:text-white">
          {weeklyHoursSaved.toFixed(1)} hours
        </p>
        <div className="my-4 h-px w-full bg-emerald-200 dark:bg-emerald-800" />
        <p className="text-sm text-zinc-600 dark:text-zinc-400">Value of manual time</p>
        <p className="text-3xl font-bold text-emerald-600">${weeklyCostManual.toFixed(0)}/week</p>
        <div className="my-4 h-px w-full bg-emerald-200 dark:bg-emerald-800" />
        <p className="text-sm text-zinc-600 dark:text-zinc-400">Application credit pack estimate</p>
        <p className="text-lg font-semibold text-zinc-900 dark:text-white">${creditCost}</p>
        <div className="mt-4 rounded-xl bg-emerald-600 px-4 py-2 text-white font-bold">
          {roi > 0 ? `${roi}% illustrative ROI` : "Illustrative comparison"} &mdash; difference $
          {savings > 0 ? savings.toFixed(0) : "0"}/week
        </div>
      </div>
    </div>
  );
}

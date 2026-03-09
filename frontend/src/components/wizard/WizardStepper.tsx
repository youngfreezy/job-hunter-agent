// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { cn } from "@/lib/utils";
import { Check } from "lucide-react";

interface WizardStepperProps {
  steps: { label: string; description?: string }[];
  currentStep: number;
}

export function WizardStepper({ steps, currentStep }: WizardStepperProps) {
  return (
    <nav aria-label="Form progress" className="mb-8">
      <ol className="flex items-center w-full">
        {steps.map((step, index) => {
          const isCompleted = index < currentStep;
          const isCurrent = index === currentStep;

          return (
            <li
              key={step.label}
              className={cn("flex items-center", index < steps.length - 1 && "flex-1")}
            >
              <div className="flex flex-col items-center">
                <div
                  className={cn(
                    "w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold border-2 transition-colors",
                    isCompleted &&
                      "bg-zinc-900 dark:bg-white border-zinc-900 dark:border-white text-white dark:text-zinc-900",
                    isCurrent && "border-zinc-900 dark:border-white text-zinc-900 dark:text-white",
                    !isCompleted &&
                      !isCurrent &&
                      "border-zinc-300 dark:border-zinc-700 text-zinc-400"
                  )}
                >
                  {isCompleted ? <Check className="w-5 h-5" /> : index + 1}
                </div>
                <span
                  className={cn(
                    "text-xs mt-2 text-center whitespace-nowrap",
                    isCurrent || isCompleted
                      ? "text-zinc-900 dark:text-white font-medium"
                      : "text-zinc-400"
                  )}
                >
                  {step.label}
                </span>
              </div>
              {index < steps.length - 1 && (
                <div
                  className={cn(
                    "flex-1 h-0.5 mx-4",
                    isCompleted ? "bg-zinc-900 dark:bg-white" : "bg-zinc-200 dark:bg-zinc-800"
                  )}
                />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

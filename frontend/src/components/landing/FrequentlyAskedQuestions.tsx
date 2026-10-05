// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useState } from "react";

import { faqs } from "./content";

export function FrequentlyAskedQuestions() {
  const [openFaq, setOpenFaq] = useState<number | null>(null);
  return (<>
    {/* FAQ */}
    <section id="faq" className="px-6 py-20 bg-white dark:bg-zinc-900/50">
      <div className="mx-auto max-w-3xl">
        <h2 className="mb-10 text-center text-3xl font-bold">Frequently Asked Questions</h2>
        <div className="space-y-3">
          {faqs.map((faq, i) => (
            <div
              key={faq.q}
              className="rounded-2xl border border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950 overflow-hidden"
            >
              <button
                className="flex w-full items-center justify-between p-5 text-left"
                onClick={() => setOpenFaq(openFaq === i ? null : i)}
              >
                <h3 className="font-semibold text-zinc-900 dark:text-white pr-4">{faq.q}</h3>
                <svg
                  className={`h-5 w-5 shrink-0 text-zinc-400 transition-transform ${openFaq === i ? "rotate-180" : ""
                    }`}
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M19.5 8.25l-7.5 7.5-7.5-7.5"
                  />
                </svg>
              </button>
              {openFaq === i && (
                <div className="px-5 pb-5">
                  <p className="text-sm leading-6 text-zinc-600 dark:text-zinc-400">{faq.a}</p>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </section>

  </>);
}

// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import Link from "next/link";

import { pricingPacks } from "./content";

export function PricingSection() {
  return (<>
    {/* Pricing */}
    <section id="pricing" className="px-6 py-20">
      <div className="mx-auto max-w-6xl">
        <div className="mb-10 text-center">
          <h2 className="text-3xl font-bold">Simple, Flexible Pricing</h2>
          <p className="mt-2 text-zinc-600 dark:text-zinc-400">
            Start free. Buy credit packs or go unlimited. Successful applications cost 1 credit,
            partial attempts just 0.5.
          </p>
        </div>

        <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
          {pricingPacks.map((plan) => (
            <Card
              key={plan.name}
              className={
                "relative flex h-full flex-col rounded-[32px] bg-white/95 shadow-[0_18px_48px_-32px_rgba(15,23,42,0.28)] dark:bg-zinc-950 " +
                (plan.popular
                  ? "border-2 border-zinc-900 dark:border-white"
                  : "border-zinc-200 dark:border-zinc-800")
              }
            >
              {plan.popular && (
                <div className="absolute -top-3 left-6">
                  <Badge>Most Popular</Badge>
                </div>
              )}
              <CardHeader className="pb-4">
                <CardTitle className="text-2xl">{plan.name}</CardTitle>
                <p className="text-sm text-zinc-500 dark:text-zinc-400">{plan.summary}</p>
                {"perDay" in plan && plan.perDay ? (
                  <div className="pt-2">
                    <span className="text-4xl font-bold text-emerald-600 dark:text-emerald-400">
                      {(plan as { perDay: string }).perDay.replace("/day", "")}
                    </span>
                    <span className="ml-1 text-lg font-semibold text-emerald-600 dark:text-emerald-400">
                      /day
                    </span>
                    <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                      {plan.apps === -1
                        ? `${plan.priceLabel}/mo billed monthly`
                        : `${plan.priceLabel} one-time`}
                    </p>
                  </div>
                ) : (
                  <div className="pt-2">
                    <span className="text-4xl font-bold">{plan.priceLabel}</span>
                  </div>
                )}
                <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                  {plan.apps === -1
                    ? "Up to 100 applications/month"
                    : plan.apps === 3
                      ? "3 free applications"
                      : `${plan.apps} credits`}
                </p>
                {plan.price > 0 && (
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">
                    Saves ~
                    {plan.apps === -1
                      ? "60"
                      : plan.apps <= 10
                        ? "5"
                        : plan.apps <= 50
                          ? "25"
                          : "50"}
                    + hours of manual applications
                  </p>
                )}
              </CardHeader>
              <CardContent className="flex flex-1 flex-col">
                <ul className="mb-6 space-y-3">
                  {plan.features.map((feature) => (
                    <li
                      key={feature}
                      className="flex items-start gap-2 text-sm text-zinc-700 dark:text-zinc-300"
                    >
                      <span className="mt-0.5 text-emerald-600">&#10003;</span>
                      <span>{feature}</span>
                    </li>
                  ))}
                </ul>
                <div className="mt-auto">
                  <Link href="/session/new" className="block">
                    <Button
                      className="w-full"
                      variant={plan.popular ? "default" : "outline"}
                      data-umami-event="cta-select-plan"
                      data-umami-event-plan={plan.name.toLowerCase().replace(" ", "-")}
                    >
                      {plan.cta}
                    </Button>
                  </Link>
                  <p className="mt-2 text-center text-xs text-zinc-400">
                    No credit card required
                  </p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        <p className="mt-4 text-center text-sm font-medium text-emerald-600 dark:text-emerald-400">
          30-day money-back guarantee on all paid plans. No questions asked.
        </p>

        <p className="mt-3 text-center text-sm text-zinc-500 dark:text-zinc-400">
          Also available: 100 credits for $179.99 ($1.80/credit). Need more?{" "}
          <a
            href="mailto:support@jobhunteragent.com"
            className="underline hover:text-zinc-900 dark:hover:text-white"
          >
            Contact us
          </a>{" "}
          for volume pricing.
        </p>
      </div>
    </section>

  </>);
}

// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { listMarketplaceAgents, type MarketplaceAgent } from "@/lib/api";

const ICON_MAP: Record<string, string> = {
  briefcase: "💼",
  compass: "🧭",
  mic: "🎤",
  rocket: "🚀",
  bot: "🤖",
};

const CATEGORIES = [
  { value: "", label: "All" },
  { value: "career", label: "Career" },
  { value: "interview", label: "Interview" },
  { value: "freelance", label: "Freelance" },
  { value: "resume", label: "Resume" },
  { value: "networking", label: "Networking" },
];

function StarRating({ rating, count }: { rating: number; count: number }) {
  const full = Math.floor(rating);
  const half = rating - full >= 0.5;
  return (
    <span className="flex items-center gap-1 text-sm text-muted-foreground">
      {[...Array(5)].map((_, i) => (
        <span
          key={i}
          className={
            i < full
              ? "text-yellow-500"
              : i === full && half
              ? "text-yellow-400"
              : "text-gray-300 dark:text-gray-600"
          }
        >
          ★
        </span>
      ))}
      <span className="ml-1">
        {rating > 0 ? rating.toFixed(1) : "—"} ({count})
      </span>
    </span>
  );
}

export default function MarketplacePage() {
  const [agents, setAgents] = useState<MarketplaceAgent[]>([]);
  const [loading, setLoading] = useState(true);
  const [category, setCategory] = useState("");

  useEffect(() => {
    listMarketplaceAgents()
      .then(setAgents)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(
    () => (category ? agents.filter((a) => a.category === category) : agents),
    [agents, category]
  );

  return (
    <main className="mx-auto max-w-5xl px-4 py-10">
      <h1 className="text-2xl font-bold">Agent Marketplace</h1>
      <p className="mt-1 text-muted-foreground">
        Browse AI agents that automate every step of your job search.
      </p>

      {/* Category filter */}
      <div className="mt-6 flex flex-wrap gap-2">
        {CATEGORIES.map((cat) => (
          <button
            key={cat.value}
            onClick={() => setCategory(cat.value)}
            className={`px-3 py-1.5 text-sm rounded-full border transition-colors ${
              category === cat.value
                ? "bg-blue-600 text-white border-blue-600"
                : "bg-background text-muted-foreground border-border hover:border-blue-300"
            }`}
          >
            {cat.label}
          </button>
        ))}
      </div>

      {/* Agent grid */}
      {loading ? (
        <div className="mt-8 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-52 bg-muted rounded-xl animate-pulse" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <p className="mt-8 text-muted-foreground">No agents found in this category.</p>
      ) : (
        <div className="mt-8 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((agent) => (
            <Link
              key={agent.slug}
              href={`/marketplace/${agent.slug}`}
              className="block rounded-xl border border-border bg-card p-5 hover:border-blue-300 hover:shadow-md transition-all"
            >
              <div className="flex items-start justify-between">
                <span className="text-2xl">{ICON_MAP[agent.icon] || "🤖"}</span>
                <span className="px-2 py-0.5 text-xs rounded-full bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-400">
                  {agent.credit_cost} cr
                </span>
              </div>
              <h3 className="mt-3 text-lg font-semibold">{agent.name}</h3>
              <p className="mt-1 text-sm text-muted-foreground line-clamp-2">
                {agent.description}
              </p>
              <div className="mt-3 flex items-center justify-between">
                <StarRating rating={agent.avg_rating} count={agent.rating_count} />
                <span className="text-xs text-muted-foreground">
                  {agent.total_uses} uses
                </span>
              </div>
              {agent.is_builtin && (
                <span className="mt-2 inline-block text-xs text-emerald-600 dark:text-emerald-400 font-medium">
                  Built-in
                </span>
              )}
            </Link>
          ))}
        </div>
      )}

      {/* Coming soon CTA */}
      <div className="mt-12 rounded-xl border border-dashed border-border p-6 text-center">
        <p className="text-lg font-semibold">Build Your Own Agent</p>
        <p className="mt-1 text-sm text-muted-foreground">
          The Agent SDK is coming soon. Create custom AI agents and share them on the marketplace.
        </p>
        <Link
          href="/developer"
          className="mt-3 inline-block px-4 py-2 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors"
        >
          Developer Portal
        </Link>
      </div>
    </main>
  );
}

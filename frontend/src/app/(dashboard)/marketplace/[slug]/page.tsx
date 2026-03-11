// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { toast } from "sonner";
import {
  getMarketplaceAgent,
  submitAgentReview,
  listAgentReviews,
  type MarketplaceAgent,
  type AgentReview,
} from "@/lib/api";
import { Button } from "@/components/ui/button";

const ICON_MAP: Record<string, string> = {
  briefcase: "💼",
  compass: "🧭",
  mic: "🎤",
  rocket: "🚀",
  bot: "🤖",
};

function StarInput({
  value,
  onChange,
}: {
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex gap-1">
      {[1, 2, 3, 4, 5].map((i) => (
        <button
          key={i}
          type="button"
          onClick={() => onChange(i)}
          className={`text-2xl transition-colors ${
            i <= value ? "text-yellow-500" : "text-gray-300 dark:text-gray-600"
          }`}
        >
          ★
        </button>
      ))}
    </div>
  );
}

export default function AgentDetailPage() {
  const { slug } = useParams<{ slug: string }>();
  const router = useRouter();
  const [agent, setAgent] = useState<MarketplaceAgent | null>(null);
  const [reviews, setReviews] = useState<AgentReview[]>([]);
  const [loading, setLoading] = useState(true);

  // Review form
  const [rating, setRating] = useState(0);
  const [reviewText, setReviewText] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!slug) return;
    getMarketplaceAgent(slug)
      .then((data) => {
        setAgent(data.agent);
        setReviews(data.reviews);
      })
      .catch(() => toast.error("Failed to load agent"))
      .finally(() => setLoading(false));
  }, [slug]);

  async function handleSubmitReview() {
    if (rating === 0) {
      toast.error("Please select a rating");
      return;
    }
    setSubmitting(true);
    try {
      await submitAgentReview(slug, rating, reviewText || undefined);
      toast.success("Review submitted!");
      setRating(0);
      setReviewText("");
      // Refresh reviews
      const fresh = await listAgentReviews(slug);
      setReviews(fresh);
      // Refresh agent stats
      const data = await getMarketplaceAgent(slug);
      setAgent(data.agent);
    } catch {
      toast.error("Failed to submit review. Are you signed in?");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return null; // loading.tsx handles this
  if (!agent) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-10">
        <p className="text-muted-foreground">Agent not found.</p>
        <Link href="/marketplace" className="text-blue-600 hover:underline mt-2 inline-block">
          Back to Marketplace
        </Link>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      {/* Breadcrumb */}
      <Link
        href="/marketplace"
        className="text-sm text-muted-foreground hover:text-foreground transition-colors"
      >
        ← Marketplace
      </Link>

      {/* Header */}
      <div className="mt-4 flex items-start gap-4">
        <span className="text-4xl">{ICON_MAP[agent.icon] || "🤖"}</span>
        <div className="flex-1">
          <h1 className="text-2xl font-bold">{agent.name}</h1>
          <p className="mt-1 text-muted-foreground">{agent.description}</p>
          <div className="mt-2 flex items-center gap-4 text-sm text-muted-foreground">
            <span className="flex items-center gap-1">
              {[...Array(5)].map((_, i) => (
                <span
                  key={i}
                  className={
                    i < Math.round(agent.avg_rating)
                      ? "text-yellow-500"
                      : "text-gray-300 dark:text-gray-600"
                  }
                >
                  ★
                </span>
              ))}
              <span className="ml-1">
                {agent.avg_rating > 0 ? agent.avg_rating.toFixed(1) : "—"} ({agent.rating_count})
              </span>
            </span>
            <span>{agent.total_uses} uses</span>
            <span className="px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-400 text-xs">
              {agent.credit_cost} credit{agent.credit_cost !== 1 ? "s" : ""}
            </span>
            {agent.is_builtin && (
              <span className="text-emerald-600 dark:text-emerald-400 font-medium text-xs">
                Built-in
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Long description */}
      {agent.long_description && (
        <p className="mt-6 text-sm leading-relaxed">{agent.long_description}</p>
      )}

      {/* Pipeline stages */}
      {agent.stages && agent.stages.length > 0 && (
        <div className="mt-8">
          <h2 className="text-lg font-semibold mb-3">Pipeline Stages</h2>
          <div className="flex flex-wrap gap-2">
            {agent.stages.map((stage, i) => (
              <div
                key={stage.name}
                className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm"
              >
                <span className="flex-shrink-0 w-5 h-5 rounded-full bg-blue-600 text-white text-xs flex items-center justify-center font-medium">
                  {i + 1}
                </span>
                <div>
                  <span className="font-medium">{stage.name.replace(/_/g, " ")}</span>
                  <span className="ml-1 text-muted-foreground">— {stage.description}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Use agent button */}
      <div className="mt-8">
        <Button
          size="lg"
          onClick={() => router.push(agent.frontend_path)}
        >
          Use This Agent
        </Button>
      </div>

      {/* Reviews section */}
      <div className="mt-12 border-t border-border pt-8">
        <h2 className="text-lg font-semibold">Reviews</h2>

        {/* Review form */}
        <div className="mt-4 rounded-lg border border-border p-4 space-y-3">
          <p className="text-sm font-medium">Leave a Review</p>
          <StarInput value={rating} onChange={setRating} />
          <textarea
            value={reviewText}
            onChange={(e) => setReviewText(e.target.value)}
            placeholder="Share your experience (optional)"
            rows={3}
            maxLength={2000}
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <Button
            size="sm"
            onClick={handleSubmitReview}
            disabled={submitting || rating === 0}
          >
            {submitting ? "Submitting..." : "Submit Review"}
          </Button>
        </div>

        {/* Review list */}
        {reviews.length === 0 ? (
          <p className="mt-4 text-sm text-muted-foreground">No reviews yet. Be the first!</p>
        ) : (
          <div className="mt-4 space-y-3">
            {reviews.map((review) => (
              <div key={review.id} className="rounded-lg border border-border p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{review.user_name}</span>
                    <span className="flex">
                      {[...Array(5)].map((_, i) => (
                        <span
                          key={i}
                          className={`text-sm ${
                            i < review.rating
                              ? "text-yellow-500"
                              : "text-gray-300 dark:text-gray-600"
                          }`}
                        >
                          ★
                        </span>
                      ))}
                    </span>
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {new Date(review.created_at).toLocaleDateString()}
                  </span>
                </div>
                {review.review_text && (
                  <p className="mt-2 text-sm text-muted-foreground">{review.review_text}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}

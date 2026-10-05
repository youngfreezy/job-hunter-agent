// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { API_BASE } from "./config";
import { apiFetch, authenticatedFetch } from "./transport";

export interface MarketplaceAgent {
  id: string;
  slug: string;
  name: string;
  description: string;
  long_description: string | null;
  icon: string;
  category: string;
  credit_cost: number;
  is_builtin: boolean;
  total_uses: number;
  avg_rating: number;
  rating_count: number;
  frontend_path: string;
  stages: { name: string; description: string }[];
  created_at: string;
}

export interface AgentReview {
  id: string;
  rating: number;
  review_text: string | null;
  user_name: string;
  created_at: string;
}

export async function listMarketplaceAgents(
  category?: string
): Promise<MarketplaceAgent[]> {
  const params = category ? `?category=${encodeURIComponent(category)}` : "";
  const res = await apiFetch(`${API_BASE}/api/marketplace/agents${params}`);
  if (!res.ok) throw new Error("Failed to load agents");
  const data = await res.json();
  return data.agents;
}

export async function getMarketplaceAgent(
  slug: string
): Promise<{ agent: MarketplaceAgent; reviews: AgentReview[] }> {
  const res = await apiFetch(`${API_BASE}/api/marketplace/agents/${slug}`);
  if (!res.ok) throw new Error("Agent not found");
  return res.json();
}

export async function submitAgentReview(
  slug: string,
  rating: number,
  reviewText?: string,
  sessionId?: string
): Promise<void> {
  const res = await authenticatedFetch(`${API_BASE}/api/marketplace/agents/${slug}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      rating,
      review_text: reviewText || null,
      session_id: sessionId || null,
    }),
  });
  if (!res.ok) throw new Error("Failed to submit review");
}

export async function listAgentReviews(
  slug: string,
  limit = 20,
  offset = 0
): Promise<AgentReview[]> {
  const res = await apiFetch(
    `${API_BASE}/api/marketplace/agents/${slug}/reviews?limit=${limit}&offset=${offset}`
  );
  if (!res.ok) throw new Error("Failed to load reviews");
  const data = await res.json();
  return data.reviews;
}

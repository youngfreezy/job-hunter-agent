// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { API_BASE } from "./config";
import { authenticatedFetch } from "./transport";

export async function getWallet(): Promise<{
  balance: number;
  free_remaining: number;
  application_cost: number;
  credit_cost_submitted?: number;
  credit_cost_partial?: number;
  is_premium?: boolean;
}> {
  const res = await authenticatedFetch(`${API_BASE}/api/billing/wallet`, {});
  if (!res.ok) throw new Error("Failed to fetch wallet");
  return res.json();
}

export async function getTransactions(): Promise<{
  transactions: Array<{
    id: string;
    amount: number;
    balance_after: number;
    type: string;
    description: string;
    created_at: string | null;
  }>;
}> {
  const res = await authenticatedFetch(`${API_BASE}/api/billing/transactions`, {});
  if (!res.ok) throw new Error("Failed to fetch transactions");
  return res.json();
}

export async function updateAutoRefill(settings: {
  enabled: boolean;
  threshold: number;
  pack_id: string;
}): Promise<{ ok: boolean }> {
  const res = await authenticatedFetch(`${API_BASE}/api/billing/auto-refill`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
  if (!res.ok) throw new Error("Failed to update auto-refill settings");
  return res.json();
}

export async function createCheckout(packId: string): Promise<{ url: string }> {
  const res = await authenticatedFetch(`${API_BASE}/api/billing/checkout`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pack_id: packId }),
  });
  if (!res.ok) throw new Error("Failed to create checkout");
  return res.json();
}

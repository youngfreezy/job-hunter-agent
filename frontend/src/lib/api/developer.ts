// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { API_BASE } from "./config";
import { authenticatedFetch } from "./transport";

export interface ApiKey {
  id: string;
  key?: string; // Only present on creation
  key_prefix: string;
  name: string;
  is_active: boolean;
  last_used_at: string | null;
  created_at: string;
}

export interface Webhook {
  id: string;
  url: string;
  secret: string;
  events: string[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface WebhookDelivery {
  id: string;
  event_type: string;
  payload: Record<string, unknown>;
  response_status: number | null;
  response_body: string | null;
  success: boolean;
  delivered_at: string;
}

export async function createApiKey(name: string): Promise<ApiKey> {
  const res = await authenticatedFetch(`${API_BASE}/api/developer/api-keys`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error("Failed to create API key");
  const data = await res.json();
  return data.api_key;
}

export async function listApiKeys(): Promise<ApiKey[]> {
  const res = await authenticatedFetch(`${API_BASE}/api/developer/api-keys`, {});
  if (!res.ok) throw new Error("Failed to load API keys");
  const data = await res.json();
  return data.api_keys;
}

export async function revokeApiKey(keyId: string): Promise<void> {
  const res = await authenticatedFetch(`${API_BASE}/api/developer/api-keys/${keyId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to revoke API key");
}

export async function createWebhook(
  url: string,
  events: string[]
): Promise<Webhook> {
  const res = await authenticatedFetch(`${API_BASE}/api/developer/webhooks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, events }),
  });
  if (!res.ok) throw new Error("Failed to create webhook");
  const data = await res.json();
  return data.webhook;
}

export async function listWebhooks(): Promise<Webhook[]> {
  const res = await authenticatedFetch(`${API_BASE}/api/developer/webhooks`, {});
  if (!res.ok) throw new Error("Failed to load webhooks");
  const data = await res.json();
  return data.webhooks;
}

export async function deleteWebhook(webhookId: string): Promise<void> {
  const res = await authenticatedFetch(`${API_BASE}/api/developer/webhooks/${webhookId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to delete webhook");
}

export async function listWebhookDeliveries(
  webhookId: string,
  limit = 20
): Promise<WebhookDelivery[]> {
  const res = await authenticatedFetch(
    `${API_BASE}/api/developer/webhooks/${webhookId}/deliveries?limit=${limit}`,
    {}
  );
  if (!res.ok) throw new Error("Failed to load deliveries");
  const data = await res.json();
  return data.deliveries;
}

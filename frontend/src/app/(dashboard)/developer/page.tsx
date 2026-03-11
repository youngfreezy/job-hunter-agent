// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  createApiKey,
  listApiKeys,
  revokeApiKey,
  createWebhook,
  listWebhooks,
  deleteWebhook,
  listWebhookDeliveries,
  type ApiKey,
  type Webhook,
  type WebhookDelivery,
} from "@/lib/api";

const TABS = ["API Keys", "Webhooks"] as const;
type Tab = (typeof TABS)[number];

const WEBHOOK_EVENTS = [
  "agent.started",
  "agent.stage_changed",
  "agent.completed",
  "agent.failed",
];

export default function DeveloperPage() {
  const [tab, setTab] = useState<Tab>("API Keys");

  // API Keys state
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [newKeyName, setNewKeyName] = useState("");
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const [loadingKeys, setLoadingKeys] = useState(true);

  // Webhooks state
  const [webhooks, setWebhooks] = useState<Webhook[]>([]);
  const [webhookUrl, setWebhookUrl] = useState("");
  const [webhookEvents, setWebhookEvents] = useState<string[]>([]);
  const [loadingWebhooks, setLoadingWebhooks] = useState(true);

  // Delivery log state
  const [selectedWebhook, setSelectedWebhook] = useState<string | null>(null);
  const [deliveries, setDeliveries] = useState<WebhookDelivery[]>([]);

  useEffect(() => {
    listApiKeys()
      .then(setApiKeys)
      .catch(() => {})
      .finally(() => setLoadingKeys(false));
    listWebhooks()
      .then(setWebhooks)
      .catch(() => {})
      .finally(() => setLoadingWebhooks(false));
  }, []);

  async function handleCreateKey() {
    if (!newKeyName.trim()) return;
    try {
      const key = await createApiKey(newKeyName.trim());
      setCreatedKey(key.key || null);
      setNewKeyName("");
      setApiKeys(await listApiKeys());
      toast.success("API key created");
    } catch {
      toast.error("Failed to create API key");
    }
  }

  async function handleRevokeKey(id: string) {
    try {
      await revokeApiKey(id);
      setApiKeys(await listApiKeys());
      toast.success("API key revoked");
    } catch {
      toast.error("Failed to revoke key");
    }
  }

  async function handleCreateWebhook() {
    if (!webhookUrl.trim() || webhookEvents.length === 0) {
      toast.error("URL and at least one event are required");
      return;
    }
    try {
      await createWebhook(webhookUrl.trim(), webhookEvents);
      setWebhookUrl("");
      setWebhookEvents([]);
      setWebhooks(await listWebhooks());
      toast.success("Webhook created");
    } catch {
      toast.error("Failed to create webhook");
    }
  }

  async function handleDeleteWebhook(id: string) {
    try {
      await deleteWebhook(id);
      setWebhooks(await listWebhooks());
      if (selectedWebhook === id) {
        setSelectedWebhook(null);
        setDeliveries([]);
      }
      toast.success("Webhook deleted");
    } catch {
      toast.error("Failed to delete webhook");
    }
  }

  async function handleViewDeliveries(webhookId: string) {
    setSelectedWebhook(webhookId);
    try {
      const d = await listWebhookDeliveries(webhookId);
      setDeliveries(d);
    } catch {
      toast.error("Failed to load deliveries");
    }
  }

  function toggleEvent(event: string) {
    setWebhookEvents((prev) =>
      prev.includes(event) ? prev.filter((e) => e !== event) : [...prev, event]
    );
  }

  return (
    <main className="mx-auto max-w-4xl px-4 py-10">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Developer Portal</h1>
          <p className="mt-1 text-muted-foreground">
            Manage API keys, webhooks, and integrate with the JobHunter platform.
          </p>
        </div>
        <Link
          href="/developer/docs"
          className="text-sm text-blue-600 hover:underline"
        >
          API Docs
        </Link>
      </div>

      {/* Tabs */}
      <div className="mt-6 flex gap-2 border-b border-border">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === t
                ? "border-blue-500 text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* API Keys Tab */}
      {tab === "API Keys" && (
        <div className="mt-6 space-y-4">
          {/* Create form */}
          <div className="flex gap-2">
            <input
              value={newKeyName}
              onChange={(e) => setNewKeyName(e.target.value)}
              placeholder="Key name (e.g. Production)"
              className="flex-1 rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              onKeyDown={(e) => e.key === "Enter" && handleCreateKey()}
            />
            <Button size="sm" onClick={handleCreateKey} disabled={!newKeyName.trim()}>
              Generate Key
            </Button>
          </div>

          {/* Newly created key warning */}
          {createdKey && (
            <div className="rounded-lg border border-amber-300 bg-amber-50 dark:bg-amber-900/20 p-4">
              <p className="text-sm font-semibold text-amber-800 dark:text-amber-300">
                Copy your API key now — it won&apos;t be shown again!
              </p>
              <div className="mt-2 flex items-center gap-2">
                <code className="flex-1 rounded bg-background px-3 py-1.5 text-xs font-mono border border-border break-all">
                  {createdKey}
                </code>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    navigator.clipboard.writeText(createdKey);
                    toast.success("Copied!");
                  }}
                >
                  Copy
                </Button>
              </div>
              <button
                onClick={() => setCreatedKey(null)}
                className="mt-2 text-xs text-muted-foreground hover:text-foreground"
              >
                Dismiss
              </button>
            </div>
          )}

          {/* Key list */}
          {loadingKeys ? (
            <div className="animate-pulse space-y-2">
              {[1, 2].map((i) => (
                <div key={i} className="h-16 bg-muted rounded-lg" />
              ))}
            </div>
          ) : apiKeys.length === 0 ? (
            <p className="text-sm text-muted-foreground">No API keys yet.</p>
          ) : (
            <div className="space-y-2">
              {apiKeys.map((key) => (
                <div
                  key={key.id}
                  className="flex items-center justify-between rounded-lg border border-border p-3"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-sm">{key.name}</span>
                      <code className="text-xs text-muted-foreground font-mono">
                        {key.key_prefix}...
                      </code>
                      {!key.is_active && (
                        <span className="px-1.5 py-0.5 text-xs rounded bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400">
                          Revoked
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Created {new Date(key.created_at).toLocaleDateString()}
                      {key.last_used_at &&
                        ` · Last used ${new Date(key.last_used_at).toLocaleDateString()}`}
                    </p>
                  </div>
                  {key.is_active && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="text-red-600 border-red-200 hover:bg-red-50"
                      onClick={() => handleRevokeKey(key.id)}
                    >
                      Revoke
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Webhooks Tab */}
      {tab === "Webhooks" && (
        <div className="mt-6 space-y-4">
          {/* Create form */}
          <div className="rounded-lg border border-border p-4 space-y-3">
            <input
              value={webhookUrl}
              onChange={(e) => setWebhookUrl(e.target.value)}
              placeholder="https://your-server.com/webhook"
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <div className="flex flex-wrap gap-2">
              {WEBHOOK_EVENTS.map((event) => (
                <button
                  key={event}
                  onClick={() => toggleEvent(event)}
                  className={`px-2.5 py-1 text-xs rounded-full border transition-colors ${
                    webhookEvents.includes(event)
                      ? "bg-blue-600 text-white border-blue-600"
                      : "bg-background text-muted-foreground border-border hover:border-blue-300"
                  }`}
                >
                  {event}
                </button>
              ))}
            </div>
            <Button size="sm" onClick={handleCreateWebhook}>
              Create Webhook
            </Button>
          </div>

          {/* Webhook list */}
          {loadingWebhooks ? (
            <div className="animate-pulse space-y-2">
              {[1, 2].map((i) => (
                <div key={i} className="h-20 bg-muted rounded-lg" />
              ))}
            </div>
          ) : webhooks.length === 0 ? (
            <p className="text-sm text-muted-foreground">No webhooks configured.</p>
          ) : (
            <div className="space-y-2">
              {webhooks.map((wh) => (
                <div
                  key={wh.id}
                  className="rounded-lg border border-border p-3"
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <code className="text-sm font-mono">{wh.url}</code>
                      <div className="mt-1 flex flex-wrap gap-1">
                        {wh.events.map((e) => (
                          <span
                            key={e}
                            className="px-1.5 py-0.5 text-xs rounded bg-gray-100 dark:bg-gray-800 text-muted-foreground"
                          >
                            {e}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleViewDeliveries(wh.id)}
                      >
                        Logs
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="text-red-600 border-red-200 hover:bg-red-50"
                        onClick={() => handleDeleteWebhook(wh.id)}
                      >
                        Delete
                      </Button>
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    Secret: <code className="font-mono">{wh.secret.slice(0, 12)}...</code>
                    {" · "}
                    {wh.is_active ? "Active" : "Inactive"}
                  </p>
                </div>
              ))}
            </div>
          )}

          {/* Delivery log */}
          {selectedWebhook && (
            <div className="mt-4">
              <h3 className="text-sm font-semibold mb-2">
                Recent Deliveries
                <button
                  onClick={() => {
                    setSelectedWebhook(null);
                    setDeliveries([]);
                  }}
                  className="ml-2 text-xs text-muted-foreground hover:text-foreground"
                >
                  (close)
                </button>
              </h3>
              {deliveries.length === 0 ? (
                <p className="text-sm text-muted-foreground">No deliveries yet.</p>
              ) : (
                <div className="space-y-2">
                  {deliveries.map((d) => (
                    <div
                      key={d.id}
                      className="rounded border border-border p-2 text-xs font-mono"
                    >
                      <div className="flex items-center justify-between">
                        <span>{d.event_type}</span>
                        <span
                          className={
                            d.success
                              ? "text-emerald-600"
                              : "text-red-600"
                          }
                        >
                          {d.success ? "OK" : `Failed${d.response_status ? ` (${d.response_status})` : ""}`}
                        </span>
                      </div>
                      <p className="text-muted-foreground mt-0.5">
                        {new Date(d.delivered_at).toLocaleString()}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </main>
  );
}

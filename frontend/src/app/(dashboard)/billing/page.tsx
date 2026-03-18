// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { API_BASE, getAuthHeaders, updateAutoRefill, apiFetch } from "@/lib/api";

interface WalletData {
  balance: number;
  free_remaining: number;
  credit_cost_submitted: number;
  credit_cost_partial: number;
  auto_refill_enabled: boolean;
  auto_refill_threshold: number;
  auto_refill_pack_id: string;
  low_balance: boolean;
}

interface Pack {
  label: string;
  price_dollars: number;
  credit_amount: number;
}

interface Transaction {
  id: string;
  amount: number;
  balance_after: number;
  type: string;
  description: string;
  created_at: string | null;
}

export default function BillingPage() {
  const searchParams = useSearchParams();
  const [wallet, setWallet] = useState<WalletData | null>(null);
  const [packs, setPacks] = useState<Record<string, Pack>>({});
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [checkoutLoading, setCheckoutLoading] = useState<string | null>(null);
  const [autoRefillEnabled, setAutoRefillEnabled] = useState(false);
  const [autoRefillThreshold, setAutoRefillThreshold] = useState(5);
  const [autoRefillPackId, setAutoRefillPackId] = useState("top_up_10");
  const [autoRefillSaving, setAutoRefillSaving] = useState(false);

  const success = searchParams.get("success");
  const canceled = searchParams.get("canceled");

  useEffect(() => {
    window.umami?.track("billing-page-viewed");
    if (success) window.umami?.track("payment-success");
    if (canceled) window.umami?.track("payment-canceled");
  }, [success, canceled]);

  useEffect(() => {
    async function load() {
      try {
        const auth = await getAuthHeaders();
        const [walletRes, packsRes, txnRes] = await Promise.all([
          apiFetch(`${API_BASE}/api/billing/wallet`, { headers: auth }),
          apiFetch(`${API_BASE}/api/billing/packs`),
          apiFetch(`${API_BASE}/api/billing/transactions`, { headers: auth }),
        ]);
        if (walletRes.ok) {
          const walletData = await walletRes.json();
          setWallet(walletData);
          setAutoRefillEnabled(walletData.auto_refill_enabled ?? false);
          setAutoRefillThreshold(walletData.auto_refill_threshold ?? 5);
          setAutoRefillPackId(walletData.auto_refill_pack_id ?? "top_up_10");
        }
        if (packsRes.ok) {
          const data = await packsRes.json();
          setPacks(data.packs || {});
        }
        if (txnRes.ok) {
          const data = await txnRes.json();
          setTransactions(data.transactions || []);
        }
      } catch {
        console.error("Failed to load billing data");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  async function handleCheckout(packId: string) {
    setCheckoutLoading(packId);
    window.umami?.track("checkout-initiate", { pack: packId });
    try {
      const auth = await getAuthHeaders();
      const res = await apiFetch(`${API_BASE}/api/billing/checkout`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({
          pack_id: packId,
          success_url: `${window.location.origin}/billing?success=true`,
          cancel_url: `${window.location.origin}/billing?canceled=true`,
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        alert(err.detail || "Checkout failed");
        return;
      }
      const data = await res.json();
      if (data.url) {
        const redirectUrl = new URL(data.url);
        if (redirectUrl.hostname.endsWith(".stripe.com")) {
          window.location.href = data.url;
        } else {
          alert("Invalid checkout URL");
        }
      }
    } catch {
      alert("Failed to create checkout session");
    } finally {
      setCheckoutLoading(null);
    }
  }

  async function handleSaveAutoRefill() {
    setAutoRefillSaving(true);
    try {
      await updateAutoRefill({
        enabled: autoRefillEnabled,
        threshold: autoRefillThreshold,
        pack_id: autoRefillPackId,
      });
      toast.success("Auto-refill settings saved");
    } catch {
      alert("Failed to save auto-refill settings");
    } finally {
      setAutoRefillSaving(false);
    }
  }

  if (loading) return null;

  const mainPacks = ["10", "50", "100"];
  const topUpPacks = ["top_up_5", "top_up_10", "top_up_25"];

  return (
    <main className="mx-auto max-w-3xl px-4 py-10 space-y-8">
      <h1 className="text-2xl font-bold">Billing</h1>

      {success && (
        <div className="bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800 text-green-700 dark:text-green-300 px-4 py-3 rounded text-sm">
          Payment successful! Your wallet has been credited.
        </div>
      )}
      {canceled && (
        <div className="bg-yellow-50 dark:bg-yellow-950 border border-yellow-200 dark:border-yellow-800 text-yellow-700 dark:text-yellow-300 px-4 py-3 rounded text-sm">
          Checkout was canceled.
        </div>
      )}

      {/* Low Balance Banner */}
      {wallet?.low_balance && (
        <div className="bg-orange-50 dark:bg-orange-950 border border-orange-200 dark:border-orange-800 text-orange-700 dark:text-orange-300 px-4 py-3 rounded text-sm flex items-center justify-between">
          <span>
            Your balance is low ({wallet.balance.toFixed(1)} credits). Refill with{" "}
            {packs[wallet.auto_refill_pack_id]?.label ?? "credits"}?
          </span>
          <Button
            size="sm"
            onClick={() => handleCheckout(wallet.auto_refill_pack_id)}
            disabled={checkoutLoading === wallet.auto_refill_pack_id}
          >
            {checkoutLoading === wallet.auto_refill_pack_id ? "Loading..." : "Refill Now"}
          </Button>
        </div>
      )}

      {/* Wallet Balance */}
      <Card className="border-blue-200 bg-blue-50/60 dark:border-blue-900 dark:bg-blue-950/20">
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-zinc-500">Credit Balance</p>
              <p className="text-3xl font-bold mt-1">
                {wallet?.balance.toFixed(1) ?? "0"}{" "}
                <span className="text-base font-normal text-zinc-400">credits</span>
              </p>
            </div>
            <div className="text-right">
              <p className="text-sm text-zinc-500">Free applications</p>
              <p className="text-2xl font-bold text-green-600">{wallet?.free_remaining ?? 0}</p>
            </div>
          </div>
          <p className="text-xs text-zinc-400 mt-3">
            Successful applications use 1 credit. Partial attempts use 0.5 credits. Skipped jobs are
            free. Free applications are used first.
          </p>
        </CardContent>
      </Card>

      {/* Social Proof */}
      <div className="rounded-xl border border-blue-200/60 bg-blue-50/50 dark:border-blue-900/40 dark:bg-blue-950/20 px-5 py-4">
        <div className="grid grid-cols-3 gap-2 sm:gap-4 text-center">
          <div>
            <p className="text-xl font-bold text-zinc-900 dark:text-white">1,200+</p>
            <p className="text-xs text-zinc-500">Job seekers helped</p>
          </div>
          <div>
            <p className="text-xl font-bold text-emerald-600">34%</p>
            <p className="text-xs text-zinc-500">Avg callback rate</p>
          </div>
          <div>
            <p className="text-xl font-bold text-zinc-900 dark:text-white">4.8/5</p>
            <p className="text-xs text-zinc-500">Satisfaction rating</p>
          </div>
        </div>
      </div>

      {/* Application Packs */}
      <div>
        <h2 className="text-lg font-semibold mb-3">Application Packs</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {mainPacks.map((id) => {
            const pack = packs[id];
            if (!pack) return null;
            const perCredit = (pack.price_dollars / pack.credit_amount).toFixed(2);
            const perDayMap: Record<string, string> = {
              "10": "$0.50/day",
              "50": "$2.00/day",
              "100": "$3.67/day",
            };
            return (
              <Card key={id} className="relative">
                {id === "50" && (
                  <Badge className="absolute -top-2 left-4 bg-blue-600">Most Popular</Badge>
                )}
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">{pack.label}</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-2xl font-bold">${pack.price_dollars}</p>
                  <p className="text-xs text-zinc-500 mt-1">${perCredit}/credit</p>
                  {perDayMap[id] && (
                    <p className="text-xs text-emerald-600 font-medium mt-0.5">
                      That&apos;s just {perDayMap[id]}
                    </p>
                  )}
                  <Button
                    className="w-full mt-4"
                    size="sm"
                    onClick={() => handleCheckout(id)}
                    disabled={checkoutLoading === id}
                  >
                    {checkoutLoading === id ? "Loading..." : "Buy"}
                  </Button>
                </CardContent>
              </Card>
            );
          })}
        </div>
        <p className="mt-3 text-center text-sm font-medium text-emerald-600 dark:text-emerald-400">
          30-day money-back guarantee on all packs. No questions asked.
        </p>
      </div>

      {/* Unlimited Plan */}
      <Card className="border-2 border-zinc-900 dark:border-white">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">Unlimited Monthly</CardTitle>
            <Badge variant="secondary">Best for active searchers</Badge>
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex items-baseline gap-2">
            <p className="text-2xl font-bold">$149.99</p>
            <span className="text-sm text-zinc-500">/month</span>
          </div>
          <p className="text-xs text-emerald-600 font-medium mt-0.5">That&apos;s just $5.00/day</p>
          <p className="text-xs text-zinc-500 mt-1">
            Up to 100 applications/month. Cancel anytime.
          </p>
          <Button
            className="w-full mt-4"
            size="sm"
            onClick={async () => {
              setCheckoutLoading("unlimited");
              try {
                const auth = await getAuthHeaders();
                const res = await apiFetch(`${API_BASE}/api/billing/subscribe`, {
                  method: "POST",
                  headers: { "Content-Type": "application/json", ...auth },
                  body: JSON.stringify({
                    success_url: `${window.location.origin}/billing?success=true`,
                    cancel_url: `${window.location.origin}/billing?canceled=true`,
                  }),
                });
                if (!res.ok) {
                  const err = await res.json();
                  alert(err.detail || "Subscription failed");
                  return;
                }
                const data = await res.json();
                if (data.url) {
                  const redirectUrl = new URL(data.url);
                  if (redirectUrl.hostname.endsWith(".stripe.com")) {
                    window.location.href = data.url;
                  } else {
                    alert("Invalid checkout URL");
                  }
                }
              } catch {
                alert("Failed to create subscription checkout");
              } finally {
                setCheckoutLoading(null);
              }
            }}
            disabled={checkoutLoading === "unlimited"}
          >
            {checkoutLoading === "unlimited" ? "Loading..." : "Go Unlimited"}
          </Button>
        </CardContent>
      </Card>

      {/* Top-ups */}
      <div>
        <h2 className="text-lg font-semibold mb-3">Quick Top-up</h2>
        <div className="flex flex-wrap gap-3">
          {topUpPacks.map((id) => {
            const pack = packs[id];
            if (!pack) return null;
            return (
              <Button
                key={id}
                variant="outline"
                size="sm"
                onClick={() => handleCheckout(id)}
                disabled={checkoutLoading === id}
              >
                {checkoutLoading === id ? "..." : pack.label}
              </Button>
            );
          })}
        </div>
      </div>

      {/* Auto-Refill Settings */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Auto-Refill</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <label className="flex items-center gap-3 cursor-pointer">
            <button
              type="button"
              role="switch"
              aria-checked={autoRefillEnabled}
              onClick={() => {
                const next = !autoRefillEnabled;
                setAutoRefillEnabled(next);
                if (!next) {
                  // Save immediately when disabling
                  updateAutoRefill({
                    enabled: false,
                    threshold: autoRefillThreshold,
                    pack_id: autoRefillPackId,
                  }).catch(() => {});
                }
              }}
              className={`relative inline-flex h-6 w-11 shrink-0 rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                autoRefillEnabled ? "bg-blue-600" : "bg-zinc-200 dark:bg-zinc-700"
              }`}
            >
              <span
                className={`pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow-lg ring-0 transition-transform ${
                  autoRefillEnabled ? "translate-x-5" : "translate-x-0"
                }`}
              />
            </button>
            <span className="text-sm font-medium">Auto-refill credits</span>
          </label>

          {autoRefillEnabled && (
            <div className="space-y-3 pl-14">
              <div>
                <label className="text-xs text-zinc-500 block mb-1">
                  Refill when balance drops below
                </label>
                <div className="flex items-center gap-2">
                  <Input
                    type="number"
                    min={1}
                    max={50}
                    value={autoRefillThreshold}
                    onChange={(e) => setAutoRefillThreshold(Number(e.target.value))}
                    className="w-20"
                  />
                  <span className="text-sm text-zinc-400">credits</span>
                </div>
              </div>
              <div>
                <label className="text-xs text-zinc-500 block mb-1">Refill pack</label>
                <select
                  value={autoRefillPackId}
                  onChange={(e) => setAutoRefillPackId(e.target.value)}
                  className="flex h-9 rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                >
                  {Object.entries(packs).map(([id, pack]) => (
                    <option key={id} value={id}>
                      {pack.label} — ${pack.price_dollars}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex items-center gap-2">
                <Button size="sm" onClick={handleSaveAutoRefill} disabled={autoRefillSaving}>
                  {autoRefillSaving ? "Saving..." : "Save"}
                </Button>
              </div>
            </div>
          )}

          {!autoRefillEnabled && (
            <p className="text-xs text-zinc-400">
              Enable to get a one-click refill prompt when your balance is low.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Transaction History */}
      <div>
        <h2 className="text-lg font-semibold mb-3">Transaction History</h2>
        {transactions.length === 0 ? (
          <p className="text-sm text-zinc-500">No transactions yet.</p>
        ) : (
          <div className="space-y-2">
            {transactions.map((tx) => (
              <div
                key={tx.id}
                className="flex items-center justify-between border rounded-lg px-4 py-3"
              >
                <div>
                  <p className="text-sm font-medium">{tx.description || tx.type}</p>
                  <p className="text-xs text-zinc-400">
                    {tx.created_at ? new Date(tx.created_at).toLocaleDateString() : ""}
                  </p>
                </div>
                <div className="text-right">
                  <p
                    className={`text-sm font-bold ${
                      tx.type === "free_application"
                        ? "text-blue-500"
                        : tx.amount > 0
                        ? "text-green-600"
                        : tx.type === "application_partial"
                        ? "text-amber-500"
                        : "text-red-500"
                    }`}
                  >
                    {tx.type === "free_application" ? (
                      <span className="text-[10px] font-medium border border-blue-300 rounded px-1.5 py-0.5">
                        FREE
                      </span>
                    ) : (
                      <>
                        {tx.amount > 0 ? "+" : ""}
                        {Math.abs(tx.amount).toFixed(1)} cr
                        {tx.type === "application_partial" && (
                          <span className="ml-1.5 text-[10px] font-normal text-amber-500 border border-amber-300 rounded px-1 py-0.5">
                            partial
                          </span>
                        )}
                      </>
                    )}
                  </p>
                  <p className="text-xs text-zinc-400">Balance: {tx.balance_after.toFixed(1)} cr</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}

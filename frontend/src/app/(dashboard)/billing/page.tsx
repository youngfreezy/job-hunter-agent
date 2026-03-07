"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface WalletData {
  balance: number;
  free_remaining: number;
  application_cost: number;
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

  const success = searchParams.get("success");
  const canceled = searchParams.get("canceled");

  useEffect(() => {
    if (success) window.umami?.track("payment-success");
    if (canceled) window.umami?.track("payment-canceled");
  }, [success, canceled]);

  useEffect(() => {
    async function load() {
      try {
        const [walletRes, packsRes, txnRes] = await Promise.all([
          fetch(`${API_BASE}/api/billing/wallet`),
          fetch(`${API_BASE}/api/billing/packs`),
          fetch(`${API_BASE}/api/billing/transactions`),
        ]);
        if (walletRes.ok) setWallet(await walletRes.json());
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
      const res = await fetch(`${API_BASE}/api/billing/checkout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
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
      if (data.url) window.location.href = data.url;
    } catch {
      alert("Failed to create checkout session");
    } finally {
      setCheckoutLoading(null);
    }
  }

  if (loading) return null;

  const mainPacks = ["20", "50", "100"];
  const topUpPacks = ["top_up_10", "top_up_25", "top_up_50"];

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

      {/* Wallet Balance */}
      <Card className="border-blue-200 bg-blue-50/60 dark:border-blue-900 dark:bg-blue-950/20">
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-zinc-500">Wallet Balance</p>
              <p className="text-3xl font-bold mt-1">
                ${wallet?.balance.toFixed(2) ?? "0.00"}
              </p>
            </div>
            <div className="text-right">
              <p className="text-sm text-zinc-500">Free applications</p>
              <p className="text-2xl font-bold text-green-600">
                {wallet?.free_remaining ?? 0}
              </p>
            </div>
          </div>
          <p className="text-xs text-zinc-400 mt-3">
            Each application costs ${wallet?.application_cost ?? "1.99"}. Free applications are used first.
          </p>
        </CardContent>
      </Card>

      {/* Application Packs */}
      <div>
        <h2 className="text-lg font-semibold mb-3">Application Packs</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {mainPacks.map((id) => {
            const pack = packs[id];
            if (!pack) return null;
            const perApp = (pack.price_dollars / parseInt(id)).toFixed(2);
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
                  <p className="text-xs text-zinc-500 mt-1">${perApp}/application</p>
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
      </div>

      {/* Top-ups */}
      <div>
        <h2 className="text-lg font-semibold mb-3">Quick Top-up</h2>
        <div className="flex gap-3">
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
                    {tx.created_at
                      ? new Date(tx.created_at).toLocaleDateString()
                      : ""}
                  </p>
                </div>
                <div className="text-right">
                  <p
                    className={`text-sm font-bold ${
                      tx.amount >= 0
                        ? "text-green-600"
                        : "text-red-500"
                    }`}
                  >
                    {tx.amount >= 0 ? "+" : ""}${Math.abs(tx.amount).toFixed(2)}
                  </p>
                  <p className="text-xs text-zinc-400">
                    Balance: ${tx.balance_after.toFixed(2)}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}

# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Billing routes: wallet, transactions, Stripe checkout, webhooks.

Pricing (credit-based):
  - Successful application: 1 credit
  - Partial attempt (work done, form didn't complete): 0.5 credits
  - Skipped (duplicate, rate-limited, no work done): 0 credits
  - 3 free applications for new users
  - Packs: 20 credits ($29.99), 50 credits ($64.99), 100 credits ($119.99)
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.gateway.deps import get_current_user
from backend.shared.billing_store import (
    credit_wallet,
    get_stripe_customer_id,
    get_transactions,
    get_wallet,
    update_auto_refill_settings,
)
from backend.shared.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])

# Pack definitions (credit-based)
PACKS = {
    "20": {"label": "20 Credits", "price_dollars": 29.99, "credit_amount": 20},
    "50": {"label": "50 Credits", "price_dollars": 64.99, "credit_amount": 50},
    "100": {"label": "100 Credits", "price_dollars": 119.99, "credit_amount": 100},
    "top_up_5": {"label": "5 Credits", "price_dollars": 7.99, "credit_amount": 5},
    "top_up_10": {"label": "10 Credits", "price_dollars": 14.99, "credit_amount": 10},
    "top_up_25": {"label": "25 Credits", "price_dollars": 34.99, "credit_amount": 25},
}

# Credit costs per application outcome
CREDIT_COST_SUBMITTED = 1.0   # Successful application
CREDIT_COST_PARTIAL = 0.5     # Failed but work was done (resume tailored, cover letter, form filled)
CREDIT_COST_SKIPPED = 0.0     # No work done (duplicate, rate-limited, auth-required)


@router.get("/wallet")
async def wallet_endpoint(request: Request):
    """Return wallet balance, free applications remaining, and auto-refill info."""
    user = get_current_user(request)
    wallet = get_wallet(user["id"])
    return {
        "balance": wallet["balance"],
        "free_remaining": wallet["free_remaining"],
        "credit_cost_submitted": CREDIT_COST_SUBMITTED,
        "credit_cost_partial": CREDIT_COST_PARTIAL,
        "auto_refill_enabled": wallet["auto_refill_enabled"],
        "auto_refill_threshold": wallet["auto_refill_threshold"],
        "auto_refill_pack_id": wallet["auto_refill_pack_id"],
        "low_balance": wallet["low_balance"],
    }


@router.get("/transactions")
async def transactions_endpoint(request: Request):
    """Return recent wallet transactions."""
    user = get_current_user(request)
    txns = get_transactions(user["id"])
    return {"transactions": txns}


@router.get("/packs")
async def packs_endpoint():
    """Return available purchase packs."""
    return {
        "packs": PACKS,
        "credit_cost_submitted": CREDIT_COST_SUBMITTED,
        "credit_cost_partial": CREDIT_COST_PARTIAL,
    }


@router.put("/auto-refill")
async def update_auto_refill(request: Request):
    """Update auto-refill preferences."""
    body = await request.json()
    user = get_current_user(request)

    enabled = body.get("enabled", False)
    threshold = body.get("threshold", 5.0)
    pack_id = body.get("pack_id", "top_up_10")

    # Validate pack_id
    if pack_id not in PACKS:
        raise HTTPException(status_code=400, detail="Invalid pack ID")
    # Validate threshold
    if threshold < 1 or threshold > 50:
        raise HTTPException(status_code=400, detail="Threshold must be between 1 and 50")

    update_auto_refill_settings(user["id"], enabled, threshold, pack_id)
    return {"ok": True}


class CheckoutRequest(BaseModel):
    pack_id: str
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


@router.post("/checkout")
async def checkout_endpoint(body: CheckoutRequest, request: Request):
    """Create a Stripe Checkout session for a pack purchase."""
    settings = get_settings()
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")

    pack = PACKS.get(body.pack_id)
    if not pack:
        raise HTTPException(status_code=400, detail=f"Unknown pack: {body.pack_id}")

    import stripe
    stripe.api_key = settings.STRIPE_SECRET_KEY

    user = get_current_user(request)
    stripe_customer_id = get_stripe_customer_id(user["id"])

    try:
        checkout_kwargs = dict(
            mode="payment",
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": pack["label"]},
                    "unit_amount": int(pack["price_dollars"] * 100),
                },
                "quantity": 1,
            }],
            metadata={
                "user_id": user["id"],
                "pack_id": body.pack_id,
                "credit_amount": str(pack["credit_amount"]),
            },
            success_url=body.success_url or "http://localhost:3000/billing?success=true",
            cancel_url=body.cancel_url or "http://localhost:3000/billing?canceled=true",
        )
        if stripe_customer_id:
            checkout_kwargs["customer"] = stripe_customer_id

        session = stripe.checkout.Session.create(**checkout_kwargs)
        return {"url": session.url, "session_id": session.id}
    except Exception as e:
        logger.exception("Stripe checkout creation failed")
        raise HTTPException(status_code=500, detail="Failed to create checkout session")


@router.post("/webhook")
async def webhook_endpoint(request: Request):
    """Handle Stripe webhook events."""
    settings = get_settings()
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Webhook secret not configured")

    import stripe
    stripe.api_key = settings.STRIPE_SECRET_KEY

    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig, settings.STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        logger.warning("Webhook signature verification failed: %s", e)
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] == "checkout.session.completed":
        session_obj = event["data"]["object"]
        metadata = session_obj.get("metadata", {})
        user_id = metadata.get("user_id")
        pack_id = metadata.get("pack_id", "")

        # Validate credit_amount against PACKS definition server-side
        pack = PACKS.get(pack_id)
        if not pack:
            logger.warning("Webhook: unknown pack_id=%s, ignoring", pack_id)
            return {"received": True}
        credit_amount = pack["credit_amount"]

        if user_id and credit_amount > 0:
            credit_wallet(
                user_id=user_id,
                amount=credit_amount,
                tx_type="pack_purchase",
                reference_id=session_obj.get("id", ""),
                description=f"Pack purchase: {pack['label']}",
            )
            logger.info(
                "Credited %d credits to user %s (pack=%s)",
                credit_amount, user_id, pack_id,
            )

    return {"received": True}

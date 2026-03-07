"""Billing routes: wallet, transactions, Stripe checkout, webhooks.

Pricing:
  - $1.99 per successful application
  - 3 free applications for new users
  - Bulk packs: 20 ($29.99), 50 ($64.99), 100 ($119.99)
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.shared.billing_store import (
    credit_wallet,
    get_or_create_user,
    get_transactions,
    get_wallet,
)
from backend.shared.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])

# Pack definitions
PACKS = {
    "20": {"label": "20 Applications", "price_dollars": 29.99, "credit_amount": 39.80},
    "50": {"label": "50 Applications", "price_dollars": 64.99, "credit_amount": 99.50},
    "100": {"label": "100 Applications", "price_dollars": 119.99, "credit_amount": 199.00},
    "top_up_10": {"label": "$10 Top-up", "price_dollars": 10.00, "credit_amount": 10.00},
    "top_up_25": {"label": "$25 Top-up", "price_dollars": 25.00, "credit_amount": 25.00},
    "top_up_50": {"label": "$50 Top-up", "price_dollars": 50.00, "credit_amount": 50.00},
}

APPLICATION_COST = 1.99


@router.get("/wallet")
async def wallet_endpoint(request: Request):
    """Return wallet balance and free applications remaining."""
    user = get_or_create_user("test-user@example.com")
    wallet = get_wallet(user["id"])
    return {
        "balance": wallet["balance"],
        "free_remaining": wallet["free_remaining"],
        "application_cost": APPLICATION_COST,
    }


@router.get("/transactions")
async def transactions_endpoint(request: Request):
    """Return recent wallet transactions."""
    user = get_or_create_user("test-user@example.com")
    txns = get_transactions(user["id"])
    return {"transactions": txns}


@router.get("/packs")
async def packs_endpoint():
    """Return available purchase packs."""
    return {"packs": PACKS, "application_cost": APPLICATION_COST}


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

    user = get_or_create_user("test-user@example.com")

    try:
        session = stripe.checkout.Session.create(
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
        return {"url": session.url, "session_id": session.id}
    except Exception as e:
        logger.exception("Stripe checkout creation failed")
        raise HTTPException(status_code=500, detail=str(e))


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
        credit_amount = float(metadata.get("credit_amount", 0))

        if user_id and credit_amount > 0:
            credit_wallet(
                user_id=user_id,
                amount=credit_amount,
                tx_type="pack_purchase",
                reference_id=session_obj.get("id", ""),
                description=f"Pack purchase: {pack_id}",
            )
            logger.info(
                "Credited $%.2f to user %s (pack=%s)",
                credit_amount, user_id, pack_id,
            )

    return {"received": True}

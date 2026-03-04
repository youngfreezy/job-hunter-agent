"""Payment routes (stub).

Stripe integration is planned for Phase 4.
This module will handle:
  - POST /api/payments/checkout   -> create a Stripe Checkout session
  - POST /api/payments/webhook    -> Stripe webhook receiver
  - GET  /api/payments/usage      -> current billing-period usage
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/payments", tags=["payments"])

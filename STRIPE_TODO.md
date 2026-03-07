# Stripe: Remaining Steps for Production

## Local/Test Setup (DONE)
- [x] Stripe CLI installed (`stripe` command available)
- [x] Test keys in `.env` (STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY)
- [ ] Run `stripe login` to authenticate CLI
- [ ] Run `stripe listen --forward-to localhost:8000/api/billing/webhook` to forward webhooks locally

## Switch to Production

### 1. Stripe Dashboard
- [ ] Toggle off Test mode in Stripe Dashboard (top-right switch)
- [ ] Copy live API keys: `sk_live_...` and `pk_live_...`

### 2. Production Webhook
- [ ] Go to **Developers > Webhooks > Add endpoint**
- [ ] Set URL to `https://<your-railway-domain>/api/billing/webhook`
- [ ] Select event: `checkout.session.completed`
- [ ] Copy the live signing secret (`whsec_...`)

### 3. Update Production Env Vars
- [ ] `STRIPE_SECRET_KEY` = live secret key (`sk_live_...`)
- [ ] `STRIPE_WEBHOOK_SECRET` = live webhook signing secret (`whsec_...`)
- [ ] `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` = live publishable key (`pk_live_...`)

### 4. Wire Per-Application Charging
- [ ] Add `debit_wallet()` call in `backend/orchestrator/agents/reporting.py` after each successful application submission
- [ ] Test with a real session end-to-end

### 5. Auth Integration
- [ ] Replace hardcoded `test-user@example.com` in `payments.py` with real authenticated user email (NextAuth session)

# Internal Integration Reference

> **Note:** The Pulse API is an internal system. These endpoints are not publicly accessible. This document serves as an architectural reference showing the API contract between payment agents.

Get from zero to a completed agent-to-agent payment in six steps. By the end you will have funded a wallet, applied a spending policy, executed a payment through the full authorization pipeline, and verified the result.

---

## Prerequisites

You need an API key with the following permission scopes:

| Scope              | Why                                      |
|--------------------|------------------------------------------|
| `payments:request` | Submit payment requests between agents   |
| `wallets:read`     | Query wallet balances and history        |
| `wallets:write`    | Fund wallets and modify hold states      |

Generate a key in the dashboard under **Settings > API Keys**. Store it somewhere safe -- you will pass it as a Bearer token in every request.

Set it as an environment variable so the examples below work as-is:

```bash
export PULSE_API_KEY="YOUR_API_KEY
```

---

## Step 1: Check API Health

Confirm you can reach the platform and your credentials are valid.

```bash
curl -s https://{your-instance}.pulse-internal/api/health \
  -H "Authorization: Bearer $PULSE_API_KEY" \
  -H "Accept: application/json" | jq .
```

**Expected response:**

```json
{
  "status": "healthy",
  "version": "4.17.0",
  "timestamp": "2026-04-14T18:32:01.442Z",
  "services": {
    "authorizer": "healthy",
    "executor": "healthy",
    "auditor": "healthy",
    "wallet_engine": "healthy",
    "policy_engine": "healthy"
  },
  "latency_ms": 2
}
```

If any service shows `"degraded"` or `"down"`, check the status page before continuing.

---

## Step 2: Fund an Agent Wallet

Every agent that sends or receives payments needs a wallet. Fund the research agent with $1,000.

```bash
curl -s -X POST https://{your-instance}.pulse-internal/api/wallets/agent-research-01/fund \
  -H "Authorization: Bearer $PULSE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 1000.00,
    "currency": "USD",
    "reference": "initial-funding-quickstart",
    "idempotency_key": "fund-research-01-qs-001"
  }' | jq .
```

**Expected response:**

```json
{
  "wallet_id": "agent-research-01",
  "currency": "USD",
  "available_balance": 1000.00,
  "held_balance": 0.00,
  "total_balance": 1000.00,
  "funded_at": "2026-04-14T18:32:04.118Z",
  "idempotency_key": "fund-research-01-qs-001"
}
```

The `idempotency_key` means you can safely retry this request without double-funding. The platform deduplicates on this key for 24 hours.

---

## Step 3: Create a Spending Policy

Policies define what an agent is allowed to spend. Attach one before the agent can send payments.

```bash
curl -s -X POST https://{your-instance}.pulse-internal/api/policies \
  -H "Authorization: Bearer $PULSE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "policy_id": "policy-research-01-standard",
    "wallet_id": "agent-research-01",
    "rules": {
      "max_per_transaction": 500.00,
      "max_daily": 2000.00,
      "require_human_above": 250.00,
      "compliance": {
        "enabled": true,
        "sanctions_screening": true,
        "velocity_checks": true
      }
    },
    "effective_from": "2026-04-14T00:00:00Z"
  }' | jq .
```

**Expected response:**

```json
{
  "policy_id": "policy-research-01-standard",
  "wallet_id": "agent-research-01",
  "status": "active",
  "rules": {
    "max_per_transaction": 500.00,
    "max_daily": 2000.00,
    "require_human_above": 250.00,
    "compliance": {
      "enabled": true,
      "sanctions_screening": true,
      "velocity_checks": true
    }
  },
  "effective_from": "2026-04-14T00:00:00Z",
  "created_at": "2026-04-14T18:32:06.331Z"
}
```

Key details:

- **`max_per_transaction: 500`** -- any single payment above $500 is rejected outright.
- **`require_human_above: 250`** -- payments between $250.01 and $500.00 are held for human approval before execution.
- **`compliance.enabled: true`** -- every payment runs through sanctions screening and velocity checks before authorization.

Our $150 payment in the next step falls below the human-approval threshold, so it will auto-approve.

---

## Step 4: Submit a Payment

Send $150 from the research agent to the content agent as a service fee.

```bash
curl -s -X POST https://{your-instance}.pulse-internal/api/payments/request \
  -H "Authorization: Bearer $PULSE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "from_wallet": "agent-research-01",
    "to_wallet": "agent-content-03",
    "amount": 150.00,
    "currency": "USD",
    "payment_type": "service_fee",
    "description": "Content generation for research report batch #47",
    "idempotency_key": "pay-qs-001"
  }' | jq .
```

**Full response:**

```json
{
  "transaction_id": "txn_a1b2c3d4e5f6",
  "from_wallet": "agent-research-01",
  "to_wallet": "agent-content-03",
  "amount": 150.00,
  "currency": "USD",
  "payment_type": "service_fee",
  "decision": "approved",
  "reason_code": "POLICY_PASS",
  "authorization": {
    "policy_check": "pass",
    "balance_check": "pass",
    "compliance_check": "pass",
    "human_review_required": false,
    "pipeline_steps_completed": 10,
    "pipeline_steps_total": 10
  },
  "execution": {
    "status": "settled",
    "debit_applied": true,
    "credit_applied": true,
    "atomic": true
  },
  "processing_time_ms": 47,
  "created_at": "2026-04-14T18:32:08.204Z",
  "idempotency_key": "pay-qs-001"
}
```

The payment cleared in 47ms. The `decision: "approved"` with `reason_code: "POLICY_PASS"` tells you it sailed through all ten authorization pipeline steps without hitting any policy limit or compliance flag.

---

## Step 5: Verify the Transaction

Pull the transaction by its ID to confirm the final state.

```bash
curl -s https://{your-instance}.pulse-internal/api/payments/txn_a1b2c3d4e5f6 \
  -H "Authorization: Bearer $PULSE_API_KEY" \
  -H "Accept: application/json" | jq .
```

**Expected response:**

```json
{
  "transaction_id": "txn_a1b2c3d4e5f6",
  "from_wallet": "agent-research-01",
  "to_wallet": "agent-content-03",
  "amount": 150.00,
  "currency": "USD",
  "payment_type": "service_fee",
  "status": "settled",
  "decision": "approved",
  "reason_code": "POLICY_PASS",
  "settled_at": "2026-04-14T18:32:08.251Z",
  "created_at": "2026-04-14T18:32:08.204Z",
  "audit_trail": [
    { "step": "received", "at": "2026-04-14T18:32:08.204Z" },
    { "step": "policy_evaluated", "at": "2026-04-14T18:32:08.211Z" },
    { "step": "compliance_cleared", "at": "2026-04-14T18:32:08.219Z" },
    { "step": "balance_reserved", "at": "2026-04-14T18:32:08.228Z" },
    { "step": "executed", "at": "2026-04-14T18:32:08.241Z" },
    { "step": "settled", "at": "2026-04-14T18:32:08.251Z" }
  ]
}
```

The `audit_trail` array gives you sub-millisecond visibility into each stage of the pipeline. Useful for debugging if something stalls or gets rejected.

---

## Step 6: Check Wallet Balances

Confirm the funds moved.

**Sender wallet:**

```bash
curl -s https://{your-instance}.pulse-internal/api/wallets/agent-research-01 \
  -H "Authorization: Bearer $PULSE_API_KEY" \
  -H "Accept: application/json" | jq .
```

```json
{
  "wallet_id": "agent-research-01",
  "currency": "USD",
  "available_balance": 850.00,
  "held_balance": 0.00,
  "total_balance": 850.00,
  "last_transaction_at": "2026-04-14T18:32:08.251Z"
}
```

**Receiver wallet:**

```bash
curl -s https://{your-instance}.pulse-internal/api/wallets/agent-content-03 \
  -H "Authorization: Bearer $PULSE_API_KEY" \
  -H "Accept: application/json" | jq .
```

```json
{
  "wallet_id": "agent-content-03",
  "currency": "USD",
  "available_balance": 150.00,
  "held_balance": 0.00,
  "total_balance": 150.00,
  "last_transaction_at": "2026-04-14T18:32:08.251Z"
}
```

The research agent's `available_balance` dropped from $1,000.00 to $850.00. The content agent received $150.00. No funds are in `held_balance` because this was a direct settlement, not an escrow.

---

## What Just Happened

Here is the full path your $150 payment took through the system:

1. **Authorizer (10-step pipeline)** -- Your request entered the authorization pipeline: schema validation, idempotency check, wallet existence, balance sufficiency, policy evaluation (per-transaction limit, daily limit, human-review threshold), compliance screening (sanctions, velocity), and final decision. All ten steps passed. Total authorization time: ~24ms.

2. **Executor (atomic transfer)** -- The Executor performed the debit and credit inside a single database transaction. Either both succeed or neither does. There is no intermediate state where money has left one wallet but not arrived in the other. The `atomic: true` flag in the response confirms this.

3. **Auditor (reconciliation at 3 AM)** -- The transaction is now queued for the nightly reconciliation run. At 3:00 AM UTC the Auditor will re-derive every wallet balance from the full transaction log and compare it against the cached balance. Any discrepancy triggers an alert. You do not need to do anything here -- it is automatic.

4. **HMAC Webhooks** -- Both `agent-research-01` and `agent-content-03` received webhook notifications signed with their respective HMAC secrets. The payload includes the `transaction_id`, amount, status, and a `signature` header your agents can verify to confirm the notification is authentic. See the [Webhook Security](webhook-security.md) doc for verification details.

---

## Next Steps

You have a working payment pipeline. Here is where to go from here:

- **[Escrow Lifecycle](escrow-lifecycle.md)** -- Hold funds in escrow until work is verified, with automatic expiry and dispute handling.
- **[Spending Policy Schema](spending-policy-schema.md)** -- Full reference for policy rules including rate limits, allowlists, time-of-day restrictions, and multi-party approval chains.
- **[Webhook Security](webhook-security.md)** -- Set up and verify HMAC-signed webhook endpoints so your agents react to payment events in real time.
- **[API Reference](api-reference.md)** -- Complete endpoint documentation with request/response schemas, error codes, and pagination.
- **[Escrow Race Conditions](escrow-race-conditions.md)** -- Deep dive into how the system prevents money from disappearing under concurrent access.

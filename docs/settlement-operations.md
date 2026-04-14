# Advanced Settlement Operations

Version: 2.1.0
Status: Production
Last Updated: 2026-04-14

---

## Partial Settlements

### Partial Capture

Not every authorization needs to settle for its full amount. The most common case is partial capture: authorize a ceiling amount, then capture only what is actually owed.

Consider an agent that authorizes $1,000 against a data delivery contract. The counterparty delivers 75% of the dataset -- acceptable under the contract terms but not the full scope. The authorizing organization captures $750 and releases the remaining $250 back to the sender's available balance. No refund flow is needed because the unreleased funds were never settled. They were held, then released.

```
POST https://{your-instance}.pulse-internal/api/pulse-api/payments/{payment_id}/capture
Content-Type: application/json
Authorization: Bearer {token}
Idempotency-Key: cap-9f1a2b3c-4d5e-6f7a-8b9c-0d1e2f3a4b5c

{
  "amount": 75000,
  "currency": "USD",
  "release_remaining": true,
  "capture_reason": "partial_delivery_accepted",
  "metadata": {
    "contract_id": "ctr_abc123",
    "delivery_percentage": 75,
    "accepted_by": "agent_procurement_07"
  }
}
```

Response:

```json
{
  "payment_id": "pay_8a7b6c5d4e3f2a1b",
  "original_authorization": 100000,
  "captured_amount": 75000,
  "released_amount": 25000,
  "status": "partially_captured",
  "capture_event_id": "evt_cap_001",
  "release_event_id": "evt_rel_001",
  "captured_at": "2026-04-14T10:30:00Z",
  "released_at": "2026-04-14T10:30:00Z"
}
```

The `release_remaining` flag is the key detail. When set to `true`, any uncaptured amount is immediately released back to the sender wallet. When set to `false`, the remaining authorization stays active -- useful when you expect additional captures against the same authorization.

Multiple partial captures against a single authorization are supported up to the original authorized amount. Each capture is its own settlement event with its own audit trail. The authorization tracks cumulative captured and remaining amounts.

```
POST https://{your-instance}.pulse-internal/api/pulse-api/payments/{payment_id}/capture
Idempotency-Key: cap-second-tranche-xyz

{
  "amount": 15000,
  "currency": "USD",
  "release_remaining": false,
  "capture_reason": "supplemental_delivery"
}
```

After two captures against a $1,000 authorization ($750 + $150), the remaining $100 stays held until explicitly captured or released. Authorizations expire after the org-configured TTL (default 7 days). Expired authorizations auto-release remaining holds and emit an `authorization.expired` webhook.

### Split Settlement

Split settlement handles the case where a single payment needs to settle to multiple counterparties. This comes up constantly in marketplace scenarios: an agent purchases a composite data product, and the payment needs to split between the data provider, the curation agent, and the platform.

```
POST https://{your-instance}.pulse-internal/api/pulse-api/payments/{payment_id}/settle
Content-Type: application/json
Authorization: Bearer {token}
Idempotency-Key: split-settle-a1b2c3d4

{
  "settlement_mode": "split",
  "splits": [
    {
      "recipient_wallet_id": "wal_data_provider_01",
      "amount": 60000,
      "description": "Raw dataset delivery"
    },
    {
      "recipient_wallet_id": "wal_curation_agent_02",
      "amount": 25000,
      "description": "Data curation and validation"
    },
    {
      "recipient_wallet_id": "wal_platform_ops",
      "amount": 15000,
      "description": "Platform facilitation fee"
    }
  ],
  "metadata": {
    "original_amount": 100000,
    "split_policy": "contract_defined",
    "contract_ref": "ctr_split_789"
  }
}
```

The splits array must sum exactly to the authorized amount (or the captured amount if partial capture was used). If the sum does not match, the request fails with a `SPLIT_AMOUNT_MISMATCH` error and no funds move.

Each split recipient receives their own settlement event. The sender sees a single debit. The reconciliation record links all splits under the parent payment ID, so downstream accounting systems can trace each outflow back to its origin.

Split settlement is atomic. Either all splits succeed or none of them do. We do not support partial split settlement because it would create an irrecoverable state: some recipients paid, others not, from a single authorization. The complexity of unwinding that is not worth the marginal flexibility.

```json
{
  "payment_id": "pay_8a7b6c5d4e3f2a1b",
  "status": "settled",
  "settlement_mode": "split",
  "splits_completed": 3,
  "splits": [
    {
      "recipient_wallet_id": "wal_data_provider_01",
      "amount": 60000,
      "settlement_event_id": "evt_stl_sp_001",
      "settled_at": "2026-04-14T11:00:00Z"
    },
    {
      "recipient_wallet_id": "wal_curation_agent_02",
      "amount": 25000,
      "settlement_event_id": "evt_stl_sp_002",
      "settled_at": "2026-04-14T11:00:00Z"
    },
    {
      "recipient_wallet_id": "wal_platform_ops",
      "amount": 15000,
      "settlement_event_id": "evt_stl_sp_003",
      "settled_at": "2026-04-14T11:00:00Z"
    }
  ]
}
```

### Installment Settlement

Some contracts call for staged payments. An agent authorizes the full contract value upfront, and settlement happens in tranches on a defined schedule. This is installment settlement.

The authorization holds the full amount. Each installment captures a portion on its scheduled date. The schedule is defined at settlement initiation and enforced by Pulse Engines. Missed schedules emit alerts but do not auto-capture -- the initiating agent or org must confirm each tranche (or configure auto-capture in the installment policy).

```
POST https://{your-instance}.pulse-internal/api/pulse-api/payments/{payment_id}/installments
Content-Type: application/json
Authorization: Bearer {token}
Idempotency-Key: inst-plan-e5f6a7b8

{
  "total_amount": 300000,
  "currency": "USD",
  "installment_policy": "manual_confirm",
  "tranches": [
    {
      "tranche_number": 1,
      "amount": 100000,
      "scheduled_date": "2026-04-15",
      "description": "Phase 1 milestone"
    },
    {
      "tranche_number": 2,
      "amount": 100000,
      "scheduled_date": "2026-05-15",
      "description": "Phase 2 milestone"
    },
    {
      "tranche_number": 3,
      "amount": 100000,
      "scheduled_date": "2026-06-15",
      "description": "Final delivery"
    }
  ],
  "on_missed_schedule": "alert_and_hold",
  "expiry_after_last_tranche_days": 30
}
```

Tranches are processed sequentially. Tranche 2 cannot settle before tranche 1. If tranche 1 is skipped or cancelled, the installment plan enters a `paused` state and requires manual intervention.

When `installment_policy` is set to `auto_capture`, Pulse Engines will automatically capture each tranche on its scheduled date without requiring confirmation. This is appropriate for recurring subscription-style payments where delivery is continuous rather than milestone-based.

```json
{
  "payment_id": "pay_inst_001",
  "installment_plan_id": "ipl_9c8b7a6d",
  "status": "active",
  "total_amount": 300000,
  "captured_to_date": 0,
  "remaining": 300000,
  "tranches": [
    {
      "tranche_number": 1,
      "amount": 100000,
      "status": "scheduled",
      "scheduled_date": "2026-04-15"
    },
    {
      "tranche_number": 2,
      "amount": 100000,
      "status": "pending",
      "scheduled_date": "2026-05-15"
    },
    {
      "tranche_number": 3,
      "amount": 100000,
      "status": "pending",
      "scheduled_date": "2026-06-15"
    }
  ],
  "next_tranche": 1,
  "created_at": "2026-04-14T12:00:00Z"
}
```

---

## Batch Settlement

### The Problem with Micro-Transaction Overhead

When agents process hundreds or thousands of small payments per hour -- micropayments for API calls, data lookups, compute credits -- settling each one individually creates enormous overhead. Every settlement is a wallet debit, a wallet credit, a status update, an audit event, a webhook dispatch, and a reconciliation record. Multiply that by 10,000 transactions and you have 60,000 discrete operations that could have been 6.

Batch settlement aggregates micro-transactions into a single settlement operation.

### Creating a Batch

```
POST https://{your-instance}.pulse-internal/api/pulse-api/settlements/batch
Content-Type: application/json
Authorization: Bearer {token}
Idempotency-Key: batch-20260414-org42

{
  "org_id": "org_42",
  "batch_window": "hourly",
  "payment_ids": [
    "pay_micro_001",
    "pay_micro_002",
    "pay_micro_003",
    "pay_micro_004",
    "pay_micro_005"
  ],
  "aggregation_strategy": "net_by_counterparty",
  "metadata": {
    "batch_label": "hourly_agent_compute_credits",
    "source_agent": "agent_compute_broker_14"
  }
}
```

The `aggregation_strategy` field determines how payments are combined:

- `net_by_counterparty`: All payments to the same recipient are summed into a single settlement. If agent A sent five $10 payments to wallet B, the batch settles as a single $50 transfer.
- `gross`: Each payment settles individually but within a single atomic transaction. Useful when you need the performance benefits of batching but require individual settlement records per payment.
- `net_by_counterparty_and_currency`: Same as `net_by_counterparty` but additionally groups by currency. Required when batches contain multi-currency payments.

The response includes a batch ID that tracks the entire operation:

```json
{
  "batch_id": "btch_2026041410_org42",
  "status": "processing",
  "payment_count": 5,
  "aggregation_strategy": "net_by_counterparty",
  "estimated_settlement_count": 2,
  "created_at": "2026-04-14T10:00:00Z",
  "estimated_completion": "2026-04-14T10:00:05Z"
}
```

### Batch Configuration per Organization

Organizations can configure default batch behavior so agents do not need to specify it per request:

```
POST https://{your-instance}.pulse-internal/api/pulse-api/orgs/{org_id}/batch-config
Content-Type: application/json
Authorization: Bearer {token}

{
  "auto_batch": true,
  "batch_window": "hourly",
  "min_batch_size": 10,
  "max_batch_size": 50000,
  "aggregation_strategy": "net_by_counterparty",
  "auto_batch_threshold_amount": 100,
  "excluded_payment_types": ["escrow", "external"],
  "batch_settlement_time": "00:30"
}
```

When `auto_batch` is enabled, any payment under `auto_batch_threshold_amount` (in the smallest currency unit) is automatically queued for the next batch window instead of settling immediately. Payments above the threshold settle individually as usual.

The `batch_settlement_time` field sets the minute-past-the-hour when hourly batches execute. Setting this to `"00:30"` means batches run at XX:30 every hour. For daily batches, this becomes the time of day (e.g., `"02:00"` for 2 AM).

### Batch Webhooks and Reconciliation

A batch emits a single `settlement.batch.completed` webhook instead of individual webhooks per payment. The webhook payload contains the batch summary and a manifest of all included payments:

```json
{
  "event": "settlement.batch.completed",
  "batch_id": "btch_2026041410_org42",
  "org_id": "org_42",
  "payment_count": 5,
  "net_settlements": 2,
  "total_amount": 50000,
  "currency": "USD",
  "settlements": [
    {
      "recipient_wallet_id": "wal_vendor_alpha",
      "amount": 30000,
      "payment_ids": ["pay_micro_001", "pay_micro_002", "pay_micro_003"]
    },
    {
      "recipient_wallet_id": "wal_vendor_beta",
      "amount": 20000,
      "payment_ids": ["pay_micro_004", "pay_micro_005"]
    }
  ],
  "completed_at": "2026-04-14T10:30:02Z"
}
```

Reconciliation treats the batch as a single line item with drill-down capability. The reconciliation record includes the batch ID, total amount, net settlement count, and references to all constituent payments. Auditors can expand the batch to see individual payment details without leaving the reconciliation view.

### Batch Failure Handling

If any payment in a batch fails validation (insufficient funds, expired authorization, frozen wallet), the batch engine has two behaviors depending on configuration:

- `fail_entire_batch` (default): No payments settle. The batch returns to `failed` status with details on the failing payment. This is the safe default for financial integrity.
- `settle_valid_skip_invalid`: Valid payments settle, invalid payments are returned to their pre-batch state and flagged for manual review. This mode requires explicit opt-in because it can create split states that are harder to reconcile.

```json
{
  "batch_id": "btch_2026041410_org42",
  "status": "partial_failure",
  "settled_count": 4,
  "failed_count": 1,
  "failed_payments": [
    {
      "payment_id": "pay_micro_003",
      "failure_reason": "authorization_expired",
      "action": "returned_to_authorized"
    }
  ]
}
```

---

## Fee Engine

### Fee Types

The platform supports four fee types. Each addresses a different cost structure.

**Platform Fee (percentage-based):** A percentage of the transaction amount charged by the platform for facilitating the payment. Typically ranges from 0.5% to 3% depending on the org's pricing tier. Applied at settlement time, not at authorization.

**Processing Fee (flat):** A fixed amount per transaction regardless of payment size. Covers the base cost of processing the payment through the settlement pipeline. Common values are $0.15 to $0.50 per transaction.

**Escrow Fee (time-based):** Charged when funds are held in escrow. Calculated as a daily rate applied to the escrowed amount. This fee exists because escrowed funds consume liquidity and carry operational overhead. The fee accrues daily and is collected when the escrow resolves (either on settlement or cancellation).

**Cross-Org Fee (surcharge):** Applied when a payment crosses organizational boundaries. Covers the additional compliance checks, reconciliation complexity, and counterparty risk assessment that cross-org payments require. Can be a flat amount, a percentage, or a combination.

### Creating Fee Policies

```
POST https://{your-instance}.pulse-internal/api/pulse-api/fee-policies
Content-Type: application/json
Authorization: Bearer {token}

{
  "org_id": "org_42",
  "policy_name": "standard_agent_fees_v3",
  "effective_from": "2026-05-01T00:00:00Z",
  "fees": [
    {
      "fee_type": "platform_fee",
      "calculation": "percentage",
      "rate": 1.50,
      "min_fee": 50,
      "max_fee": 500000,
      "currency": "USD",
      "applies_to": ["instant", "escrow"]
    },
    {
      "fee_type": "processing_fee",
      "calculation": "flat",
      "amount": 25,
      "currency": "USD",
      "applies_to": ["instant", "escrow", "external"]
    },
    {
      "fee_type": "escrow_fee",
      "calculation": "daily_rate",
      "rate_bps": 5,
      "min_daily_fee": 10,
      "currency": "USD",
      "applies_to": ["escrow"]
    },
    {
      "fee_type": "cross_org_fee",
      "calculation": "tiered",
      "tiers": [
        { "up_to": 100000, "flat": 100 },
        { "up_to": 1000000, "flat": 250 },
        { "above": 1000000, "percentage": 0.10 }
      ],
      "currency": "USD",
      "applies_to": ["instant", "escrow", "external"]
    }
  ]
}
```

Response:

```json
{
  "fee_policy_id": "fp_std_v3_org42",
  "org_id": "org_42",
  "policy_name": "standard_agent_fees_v3",
  "status": "scheduled",
  "effective_from": "2026-05-01T00:00:00Z",
  "fee_count": 4,
  "created_at": "2026-04-14T14:00:00Z",
  "supersedes_policy": "fp_std_v2_org42"
}
```

Fee policies are versioned and date-effective. A new policy does not retroactively change fees on existing payments. It applies only to payments authorized after the `effective_from` timestamp. The previous policy remains active for any in-flight payments that were authorized under it.

### Fee Deduction Methods

Fees can be deducted in three ways, configured per org:

- `deduct_from_settlement`: Fees are subtracted from the settlement amount before crediting the recipient. The recipient receives the net amount. This is the most common method for marketplace payments.
- `charge_sender`: Fees are charged to the sender's wallet as a separate line item alongside the payment amount. The recipient receives the full gross amount.
- `invoice_monthly`: Fees accrue over the billing period and are invoiced to the org at month-end. No per-transaction deduction occurs. Useful for high-volume orgs that prefer consolidated billing.

```
PATCH https://{your-instance}.pulse-internal/api/pulse-api/fee-policies/{fee_policy_id}
Content-Type: application/json

{
  "deduction_method": "deduct_from_settlement",
  "invoice_config": null
}
```

### Fee Reporting in Reconciliation

Every reconciliation record includes a fee breakdown:

```json
{
  "payment_id": "pay_8a7b6c5d4e3f2a1b",
  "gross_amount": 100000,
  "fees": {
    "platform_fee": 1500,
    "processing_fee": 25,
    "escrow_fee": 0,
    "cross_org_fee": 100,
    "total_fees": 1625
  },
  "net_amount": 98375,
  "fee_policy_id": "fp_std_v3_org42",
  "deduction_method": "deduct_from_settlement"
}
```

The fee engine also generates aggregate fee reports per org, per period:

```
GET https://{your-instance}.pulse-internal/api/pulse-api/fee-policies/{fee_policy_id}/report?period=2026-04
```

```json
{
  "fee_policy_id": "fp_std_v3_org42",
  "period": "2026-04",
  "total_transactions": 12847,
  "fee_summary": {
    "platform_fee_total": 4285300,
    "processing_fee_total": 321175,
    "escrow_fee_total": 89420,
    "cross_org_fee_total": 156800,
    "grand_total": 4852695
  },
  "currency": "USD",
  "generated_at": "2026-04-14T15:00:00Z"
}
```

---

## Multi-Currency FX

### Rate Lookup at Authorization

When a payment is authorized in a currency different from the recipient's wallet currency, Pulse Engines performs an FX rate lookup at authorization time. The rate is fetched from the configured rate provider and included in the authorization response.

```
POST https://{your-instance}.pulse-internal/api/pulse-api/payments/authorize
Content-Type: application/json
Authorization: Bearer {token}

{
  "sender_wallet_id": "wal_sender_eur",
  "recipient_wallet_id": "wal_receiver_usd",
  "amount": 100000,
  "currency": "EUR",
  "fx_mode": "indicative"
}
```

```json
{
  "payment_id": "pay_fx_001",
  "authorized_amount": 100000,
  "authorized_currency": "EUR",
  "indicative_fx": {
    "target_currency": "USD",
    "rate": 1.0847,
    "indicative_target_amount": 108470,
    "rate_provider": "ecb_daily",
    "rate_timestamp": "2026-04-14T08:00:00Z",
    "rate_valid_until": "2026-04-14T20:00:00Z"
  },
  "status": "authorized"
}
```

The `fx_mode: "indicative"` means the rate shown is for informational purposes. The actual conversion happens at settlement time using the rate in effect at that moment. This is the default for instant settlement because the window between authorization and settlement is small (usually seconds).

### Rate Locking for Escrow

Escrow payments often have days or weeks between authorization and settlement. An indicative rate is useless when the settlement date is uncertain. Rate locking fixes the exchange rate at authorization time and guarantees that rate will be used at settlement, regardless of market movements.

```
POST https://{your-instance}.pulse-internal/api/pulse-api/payments/authorize
Content-Type: application/json
Authorization: Bearer {token}

{
  "sender_wallet_id": "wal_sender_eur",
  "recipient_wallet_id": "wal_receiver_usd",
  "amount": 100000,
  "currency": "EUR",
  "fx_mode": "locked",
  "escrow_expected_duration_days": 14
}
```

```json
{
  "payment_id": "pay_fx_locked_001",
  "authorized_amount": 100000,
  "authorized_currency": "EUR",
  "locked_fx": {
    "target_currency": "USD",
    "locked_rate": 1.0832,
    "guaranteed_target_amount": 108320,
    "lock_premium_bps": 15,
    "lock_cost": 162,
    "lock_expires_at": "2026-04-28T20:00:00Z",
    "rate_provider": "ecb_daily",
    "locked_at": "2026-04-14T10:00:00Z"
  },
  "status": "authorized"
}
```

Rate locks carry a premium (`lock_premium_bps`), charged in basis points, because the platform absorbs the FX risk for the duration of the lock. The premium scales with the expected escrow duration and the volatility of the currency pair. Highly volatile pairs in emerging markets carry higher lock premiums than EUR/USD.

If the escrow resolves after the lock expiration, the payment falls back to the spot rate at settlement time and the lock premium is not refunded. The lock expiration is always set to exceed the expected escrow duration by a margin (default 2x), but it is still finite.

### Cross-Currency Atomic Settlement

When a payment settles across currencies, the debit and credit must happen atomically even though they involve different currency ledgers. Pulse Engines handles this by executing the FX conversion within the same serializable transaction as the settlement:

```
Step 1:  BEGIN transaction (SERIALIZABLE)
Step 2:  Debit sender wallet: 100,000 EUR
Step 3:  Execute FX conversion at locked/spot rate
Step 4:  Credit receiver wallet: 108,320 USD (locked rate example)
Step 5:  Record FX event with rate, source, timestamp
Step 6:  Deduct FX-related fees (lock premium, FX markup)
Step 7:  COMMIT
```

If the FX conversion fails (rate provider unavailable, rate stale beyond tolerance), the entire settlement rolls back. No partial state. The payment remains authorized and settlement can be retried.

### Configurable FX Markup

Organizations can configure an FX markup that is added on top of the market rate. This is a revenue source for platforms that facilitate cross-currency payments.

```
PATCH https://{your-instance}.pulse-internal/api/pulse-api/orgs/{org_id}/fx-config
Content-Type: application/json

{
  "fx_markup_bps": 25,
  "fx_markup_cap_bps": 100,
  "preferred_rate_provider": "ecb_daily",
  "fallback_rate_provider": "reuters_spot",
  "rate_staleness_tolerance_minutes": 60,
  "supported_currencies": ["USD", "EUR", "GBP", "AED", "BRL", "JPY"],
  "lock_premium_schedule": {
    "0_7_days": 15,
    "8_14_days": 25,
    "15_30_days": 40,
    "31_plus_days": 60
  }
}
```

The `fx_markup_bps` is added to every FX conversion. The `fx_markup_cap_bps` prevents the markup from exceeding a maximum on large transactions where basis points translate to significant absolute amounts.

---

## Dead Letter Queue

### Why Payments End Up in the Dead Letter Queue

Payments enter the dead letter queue (DLQ) when they cannot be processed by the normal settlement pipeline after exhausting retry logic. The most common causes:

- Recipient wallet frozen or closed after authorization
- Insufficient funds in sender wallet at settlement time (balance changed between auth and settle)
- External rail adapter returning persistent errors (bank rejection, invalid routing)
- FX rate provider unavailable beyond staleness tolerance
- Compliance hold triggered during settlement
- Escrow resolution timeout exceeded

These are not transient failures. They are states where automated retry will not succeed without human intervention or state changes.

### Listing the Dead Letter Queue

```
GET https://{your-instance}.pulse-internal/api/pulse-api/payments/dead-letter?org_id=org_42&status=open&sort=age_desc
Authorization: Bearer {token}
```

```json
{
  "dlq_entries": [
    {
      "dlq_entry_id": "dlq_001",
      "payment_id": "pay_stuck_001",
      "original_amount": 250000,
      "currency": "USD",
      "failure_reason": "recipient_wallet_frozen",
      "failure_code": "WALLET_FROZEN",
      "first_failed_at": "2026-04-10T14:00:00Z",
      "retry_count": 3,
      "last_retry_at": "2026-04-11T02:00:00Z",
      "age_hours": 92,
      "severity": "critical",
      "assigned_to": null,
      "resolution": null
    },
    {
      "dlq_entry_id": "dlq_002",
      "payment_id": "pay_stuck_002",
      "original_amount": 5000,
      "currency": "EUR",
      "failure_reason": "external_rail_rejection",
      "failure_code": "RAIL_BANK_REJECTED",
      "first_failed_at": "2026-04-13T09:15:00Z",
      "retry_count": 5,
      "last_retry_at": "2026-04-14T09:15:00Z",
      "age_hours": 29,
      "severity": "warning",
      "assigned_to": "ops_agent_03",
      "resolution": null
    }
  ],
  "total_count": 2,
  "total_amount": 255000,
  "oldest_entry_hours": 92
}
```

### Resolution Options

Each DLQ entry can be resolved in one of four ways:

```
POST https://{your-instance}.pulse-internal/api/pulse-api/payments/dead-letter/{dlq_entry_id}/resolve
Content-Type: application/json
Authorization: Bearer {token}

{
  "action": "retry",
  "reason": "Recipient wallet unfrozen, retrying settlement",
  "resolved_by": "ops_agent_03"
}
```

**Retry:** Re-submits the payment to the settlement pipeline. Appropriate when the underlying issue has been resolved (wallet unfrozen, funds deposited, rail restored). The retry respects the original payment parameters and idempotency key.

**Cancel:** Voids the payment and releases any held funds back to the sender. Appropriate when the payment is no longer valid (contract cancelled, counterparty departed, duplicate payment identified). A `payment.cancelled` event is emitted with a reference to the DLQ entry.

**Escalate:** Assigns the entry to a higher-tier operations team or compliance review. The payment stays in the DLQ but its severity is upgraded and notifications are sent to the escalation contacts configured for the org.

**Write Off:** Marks the payment as a loss. This is the last resort for cases where funds cannot be recovered and the payment cannot be completed. Write-offs require dual authorization (two different operators must approve) and generate a compliance event for audit purposes.

```json
{
  "dlq_entry_id": "dlq_001",
  "payment_id": "pay_stuck_001",
  "resolution": "retry",
  "resolution_reason": "Recipient wallet unfrozen, retrying settlement",
  "resolved_by": "ops_agent_03",
  "resolved_at": "2026-04-14T15:30:00Z",
  "retry_result": "settlement_succeeded"
}
```

### Aging Alerts

Pulse Engines monitors DLQ entry age and triggers alerts at configurable thresholds:

| Age Threshold | Default Severity | Default Action |
|---|---|---|
| 24 hours | `warning` | Notification to org ops team |
| 72 hours | `critical` | Notification to org ops lead + platform ops |
| 7 days | `escalation` | Auto-escalate to compliance review, freeze new payments to/from affected wallets |

```
PATCH https://{your-instance}.pulse-internal/api/pulse-api/orgs/{org_id}/dlq-config
Content-Type: application/json

{
  "aging_thresholds": [
    { "hours": 24, "severity": "warning", "notify": ["ops_team"] },
    { "hours": 72, "severity": "critical", "notify": ["ops_lead", "platform_ops"] },
    { "hours": 168, "severity": "escalation", "notify": ["compliance_review"], "auto_action": "escalate" }
  ],
  "auto_freeze_on_escalation": true,
  "freeze_scope": "affected_wallets"
}
```

### SLA Tracking

Every DLQ entry tracks SLA compliance. The SLA defines maximum resolution time by severity:

```json
{
  "sla_config": {
    "warning": { "target_resolution_hours": 24 },
    "critical": { "target_resolution_hours": 8 },
    "escalation": { "target_resolution_hours": 4 }
  },
  "current_sla_status": {
    "total_open": 2,
    "within_sla": 1,
    "breaching_sla": 1,
    "sla_breach_rate_percent": 50.0
  }
}
```

SLA breach events are emitted as webhooks (`dlq.sla.breached`) and included in the org's compliance dashboard. Repeated SLA breaches can trigger automatic review of the org's payment processing configuration.

---

## Idempotency

### The Idempotency-Key Header

Every mutating endpoint in the payment API requires an `Idempotency-Key` header. This is not optional. Requests without the header are rejected with a `400 MISSING_IDEMPOTENCY_KEY` error.

The key is a client-generated string (we recommend UUID v4) that uniquely identifies the intent of the request. If the same key is sent twice, the second request returns the stored response from the first request without re-executing the operation.

```
POST https://{your-instance}.pulse-internal/api/pulse-api/payments/authorize
Content-Type: application/json
Authorization: Bearer {token}
Idempotency-Key: authz-550e8400-e29b-41d4-a716-446655440000

{
  "sender_wallet_id": "wal_sender_01",
  "recipient_wallet_id": "wal_receiver_01",
  "amount": 50000,
  "currency": "USD"
}
```

First call: processes the authorization, stores the response keyed by the idempotency key, returns `201 Created`.

Second call with same key: returns the stored response with `200 OK` and includes the `Idempotent-Replayed: true` header.

```
HTTP/1.1 200 OK
Content-Type: application/json
Idempotent-Replayed: true

{
  "payment_id": "pay_idem_001",
  "status": "authorized",
  "amount": 50000,
  "currency": "USD",
  "authorized_at": "2026-04-14T10:00:00Z"
}
```

### 24-Hour TTL

Idempotency keys are stored for 24 hours from the time of the original request. After 24 hours, the key expires and the same key can be reused (though we strongly recommend against key reuse -- generate a new key for each distinct intent).

The 24-hour window is chosen to cover retry scenarios during outages. If your system goes down for an hour, comes back up, and retries all pending requests, the idempotency layer ensures no duplicate payments are created.

### Conflict Detection

If a request is received with an idempotency key that was previously used, but the request body differs from the original, the API returns `409 Conflict` with an `IDEMPOTENCY_KEY_CONFLICT` error. This prevents a subtle class of bugs where a client reuses a key for a different payment intent.

```json
{
  "error": "IDEMPOTENCY_KEY_CONFLICT",
  "message": "Idempotency key 'authz-550e8400...' was previously used with different request parameters",
  "original_request_hash": "sha256:abc123...",
  "new_request_hash": "sha256:def456...",
  "original_payment_id": "pay_idem_001"
}
```

### Concurrent Request Handling

If two requests with the same idempotency key arrive simultaneously (within milliseconds of each other), the first request to acquire the processing lock wins. The second request receives a `429 Too Many Requests` with a `Retry-After: 2` header, instructing the client to retry after 2 seconds. By that time, the first request will have completed and the retry will receive the stored response.

---

## Payment Holds

### What Holds Do

A payment hold freezes payment activity for a specific target. No new payments can be authorized or settled involving the held target. Existing escrows continue to their natural resolution (we do not break escrow contracts mid-flight), but no new escrows can be initiated.

Holds are used for compliance investigations, fraud suspicion, regulatory requests, and internal risk management.

### Creating a Hold

```
POST https://{your-instance}.pulse-internal/api/pulse-api/holds
Content-Type: application/json
Authorization: Bearer {token}

{
  "target_type": "agent",
  "target_id": "agent_suspect_42",
  "hold_reason": "compliance_investigation",
  "hold_description": "Unusual transaction pattern detected by risk engine. Investigation ref: INV-2026-0414-001",
  "requested_by": "compliance_officer_07",
  "scope": "all_activity",
  "notify_target": false,
  "review_deadline": "2026-04-21T00:00:00Z"
}
```

The `target_type` field accepts three values:

- `agent`: Freezes all payment activity for a specific agent across all organizations.
- `org`: Freezes all payment activity for an entire organization. All agents within the org are affected.
- `fund`: Freezes a specific wallet/fund. Other wallets in the same org or agent are unaffected.

The `scope` field controls what is frozen:

- `all_activity`: No authorizations, settlements, or new escrows. This is the nuclear option.
- `outbound_only`: The target can receive payments but cannot send them.
- `inbound_only`: The target can send payments but cannot receive them. Rare, but used when a recipient is under investigation for receiving illicit funds.
- `new_authorizations_only`: Existing authorized payments can still settle, but no new authorizations are accepted. This is the gentlest hold.

```json
{
  "hold_id": "hld_001",
  "target_type": "agent",
  "target_id": "agent_suspect_42",
  "hold_reason": "compliance_investigation",
  "scope": "all_activity",
  "status": "active",
  "created_at": "2026-04-14T16:00:00Z",
  "review_deadline": "2026-04-21T00:00:00Z",
  "existing_escrows_in_flight": 3,
  "existing_authorized_payments": 7
}
```

### Existing Escrows Under Hold

When a hold is placed, existing escrows are not cancelled. This is a deliberate design decision. Escrows are contractual commitments between two parties. Unilaterally cancelling them because one party is under investigation would harm the innocent counterparty.

Instead, existing escrows proceed to their natural resolution. If the escrow settles, the funds go to the recipient's wallet -- but if the recipient is also held, the funds remain in the escrow account until the hold is resolved. If the escrow is cancelled (by the escrow terms, not by the hold), the refund goes back to the sender.

New escrow initiations involving the held target are blocked.

### Hold Audit Trail

Every hold generates a complete audit trail:

```
GET https://{your-instance}.pulse-internal/api/pulse-api/holds/{hold_id}/audit
Authorization: Bearer {token}
```

```json
{
  "hold_id": "hld_001",
  "audit_events": [
    {
      "event": "hold.created",
      "timestamp": "2026-04-14T16:00:00Z",
      "actor": "compliance_officer_07",
      "details": "Hold placed for compliance investigation INV-2026-0414-001"
    },
    {
      "event": "hold.payment_blocked",
      "timestamp": "2026-04-14T16:05:00Z",
      "details": "Blocked authorization attempt pay_attempt_099 from agent_suspect_42"
    },
    {
      "event": "hold.escrow_continued",
      "timestamp": "2026-04-14T16:10:00Z",
      "details": "Existing escrow esc_045 settled normally during hold period"
    }
  ]
}
```

### Releasing a Hold

```
DELETE https://{your-instance}.pulse-internal/api/pulse-api/holds/{hold_id}
Content-Type: application/json
Authorization: Bearer {token}

{
  "release_reason": "Investigation completed, no violations found",
  "released_by": "compliance_officer_07",
  "release_ref": "INV-2026-0414-001-CLOSED"
}
```

Hold releases are immediate. All blocked activity resumes. Any payments that were rejected during the hold period are not automatically retried -- the originating agents must resubmit them. The hold audit trail records the release event with the reason and the releasing officer.

```json
{
  "hold_id": "hld_001",
  "status": "released",
  "released_at": "2026-04-18T10:00:00Z",
  "released_by": "compliance_officer_07",
  "release_reason": "Investigation completed, no violations found",
  "hold_duration_hours": 66,
  "payments_blocked_during_hold": 12,
  "escrows_continued_during_hold": 3
}
```

### Hold Review Deadlines

Every hold has a `review_deadline`. If the hold is not released or renewed by the deadline, Pulse Engines emits a `hold.review_overdue` alert to the org's compliance team and platform operations. Holds do not auto-release on deadline -- that would defeat the purpose of a compliance hold. But the alert ensures holds are not forgotten indefinitely.

Organizations can configure maximum hold durations by hold reason:

```
PATCH https://{your-instance}.pulse-internal/api/pulse-api/orgs/{org_id}/hold-config
Content-Type: application/json

{
  "max_hold_durations": {
    "compliance_investigation": { "days": 30 },
    "fraud_suspicion": { "days": 14 },
    "regulatory_request": { "days": 90 },
    "internal_risk": { "days": 7 }
  },
  "review_reminder_interval_hours": 48,
  "require_dual_authorization_for_release": true
}
```

When `require_dual_authorization_for_release` is enabled, hold releases require approval from two different operators. The first operator initiates the release, the second confirms it. This prevents a single compromised account from releasing holds prematurely.

# Chargeback & Refund Protocol

**Protocol Version:** 1.4.0
**Last Revised:** 2026-04-11
**Status:** Production — enforced across all payment corridors
**Owner:** Payment Operations / Dispute Resolution Team

---

## Overview

This document specifies the complete chargeback, refund, and credit/debit memo lifecycle within the Pulse payment network. Every reversal of funds — whether initiated by a payer, a platform operator, or an automated Pulse Engine — flows through the pipelines described here.

We built this protocol because payment reversals are where trust breaks down. A sloppy chargeback system breeds fraud. A rigid one punishes legitimate grievances. The goal is a system that moves fast on clear-cut cases, slows down for ambiguous ones, and never loses money in the cracks between states.

Three subsystems handle reversals:

1. **Chargeback Pipeline** — adversarial process where a payer disputes a completed payment and the counterparty has a window to respond with evidence.
2. **Refund Engine** — cooperative process where either party or a platform operator initiates a return of funds.
3. **Credit/Debit Memo System** — accounting adjustments that don't map neatly to a single payment, used for billing corrections, service credits, and reconciliation adjustments.

All three share the same underlying atomic fund movement layer, the same webhook infrastructure, and the same audit trail. They differ in who initiates, what evidence is required, and how disputes are adjudicated.

---

## Chargeback Pipeline

### Initiating a Chargeback

A chargeback is filed by the paying party (or their agent) against a completed payment. The payment must be in `completed` status and within the chargeback eligibility window (default: 90 days from completion, configurable per corridor).

```
POST https://{your-instance}.pulse-internal/api/pulse-api/payments/:id/chargeback
Authorization: Bearer <token>
Content-Type: application/json
Idempotency-Key: <unique-key>

{
  "reason_code": "service_not_delivered",
  "reason_detail": "Agent was contracted to retrieve and summarize 50 SEC filings. Only 12 were returned before the task timed out. No partial delivery acknowledgment was provided.",
  "evidence": [
    {
      "type": "text",
      "content": "Task assignment specified 50 filings. Delivery record shows 12 completed. No timeout notification was sent to our endpoint.",
      "submitted_by": "org_payer_8f3a1b",
      "submitted_at": "2026-04-10T14:22:00Z"
    },
    {
      "type": "delivery_record_id",
      "content": "dlv_rec_44a8bc91e3",
      "submitted_by": "org_payer_8f3a1b",
      "submitted_at": "2026-04-10T14:22:00Z"
    }
  ],
  "requested_resolution": "full_reversal",
  "metadata": {
    "internal_ticket": "SUP-29381"
  }
}
```

**Response (201 Created):**

```json
{
  "chargeback_id": "cb_7x9mK2pL4nQ8",
  "payment_id": "pay_3fR8kW2mN9vB",
  "status": "evidence_window_open",
  "reason_code": "service_not_delivered",
  "evidence_window_closes_at": "2026-04-13T14:22:00Z",
  "created_at": "2026-04-10T14:22:00Z",
  "counterparty_org_id": "org_provider_2c7d9e",
  "amount_disputed": {
    "value": "1250.00",
    "currency": "USD"
  }
}
```

On creation, the system immediately:

1. Places a hold on the disputed amount in the counterparty's wallet (funds are frozen but not moved).
2. Sends a `payment.chargeback_filed` webhook to the counterparty.
3. Opens the evidence window (default 72 hours, configurable per corridor from 24h to 168h).
4. Notifies the filing party that the chargeback is active.

### Evidence Window

The evidence window is the counterparty's opportunity to respond. During this window:

- The counterparty can submit evidence via `POST /pulse-api/payments/:id/chargeback/evidence`.
- The filer can submit additional evidence via the same endpoint.
- Neither party can withdraw evidence once submitted.
- The window duration is fixed at creation time and cannot be extended.

We chose a hard window deliberately. In early iterations we allowed extensions, and counterparties abused them to delay resolution indefinitely. The 72-hour default is long enough for a well-organized team to gather delivery records, and short enough that payers aren't left in limbo.

```
POST https://{your-instance}.pulse-internal/api/pulse-api/payments/:id/chargeback/evidence
Authorization: Bearer <token>
Content-Type: application/json

{
  "chargeback_id": "cb_7x9mK2pL4nQ8",
  "evidence": [
    {
      "type": "delivery_record_id",
      "content": "dlv_rec_77b2cf01d8",
      "submitted_by": "org_provider_2c7d9e",
      "submitted_at": "2026-04-11T09:15:00Z"
    },
    {
      "type": "text",
      "content": "All 50 filings were processed. 12 were delivered synchronously; the remaining 38 were delivered via the async callback endpoint registered by the payer. Delivery receipts for all 38 async deliveries are attached.",
      "submitted_by": "org_provider_2c7d9e",
      "submitted_at": "2026-04-11T09:15:00Z"
    },
    {
      "type": "screenshot_reference",
      "content": "scr_ref_a4e8f912bc",
      "submitted_by": "org_provider_2c7d9e",
      "submitted_at": "2026-04-11T09:16:00Z"
    }
  ]
}
```

### Counterparty Response

Beyond submitting evidence, the counterparty can formally respond to the chargeback:

```
POST https://{your-instance}.pulse-internal/api/pulse-api/payments/:id/chargeback/respond
Authorization: Bearer <token>
Content-Type: application/json

{
  "chargeback_id": "cb_7x9mK2pL4nQ8",
  "response_type": "contest",
  "summary": "Full delivery was completed. Payer's callback endpoint returned 503 errors for the async batch, but we retried successfully and have delivery receipts for all 50 filings."
}
```

Valid `response_type` values:

| Value | Meaning |
|-------|---------|
| `contest` | Counterparty disputes the chargeback and provides evidence |
| `accept_full` | Counterparty accepts full reversal |
| `accept_partial` | Counterparty accepts partial reversal (must include `partial_amount`) |
| `no_response` | System-generated when the evidence window closes without a response |

If the counterparty does not respond before the evidence window closes, the system records a `no_response` and the chargeback proceeds to evaluation with a strong presumption in favor of the filer. We don't auto-resolve on timeout because even uncontested chargebacks should pass through the evaluation engine for pattern detection and rate monitoring.

### Automated Evaluation

Once the evidence window closes (or both parties indicate they've finished submitting evidence), the Pulse Engine evaluation pipeline kicks in.

The evaluation engine:

1. **Collects all evidence** from both parties into a structured dossier.
2. **Cross-references delivery records** — if `delivery_record_id` evidence is submitted, the engine pulls the actual delivery record from the reconciliation subsystem and checks completion status, timestamps, and acknowledgments.
3. **Checks for duplicate chargebacks** — has this payment been charged back before? Has this org filed similar chargebacks against the same counterparty?
4. **Generates a confidence score** (0-100) for each possible resolution.
5. **Auto-resolves** if confidence exceeds 85 for any resolution. Otherwise, escalates to human review.

The evaluation produces a structured assessment:

```json
{
  "chargeback_id": "cb_7x9mK2pL4nQ8",
  "assessment": {
    "recommended_resolution": "denial",
    "confidence_score": 92,
    "reasoning": [
      "Delivery records confirm all 50 items were processed and delivered.",
      "Async delivery receipts show successful delivery to payer callback endpoint.",
      "Payer's claim of non-delivery contradicts delivery record evidence.",
      "No prior chargebacks from this counterparty in the last 180 days."
    ],
    "evidence_summary": {
      "filer_evidence_count": 2,
      "counterparty_evidence_count": 3,
      "delivery_records_verified": true,
      "delivery_completion_rate": 1.0
    }
  }
}
```

### Resolution

Every chargeback resolves to exactly one of three outcomes:

| Resolution | Description | Fund Movement |
|-----------|-------------|---------------|
| `full_reversal` | Filer wins. Full disputed amount returned to filer's wallet. | Counterparty wallet debited, filer wallet credited. |
| `partial_reversal` | Split decision. A portion of the disputed amount is returned. | Partial debit/credit. Remainder released from hold. |
| `denial` | Counterparty wins. No funds moved. Hold released. | Hold on counterparty wallet released. |

Resolution is applied atomically. The fund movement, status update, and webhook dispatch happen in a single transaction. There is no state where funds are in flight between wallets.

```
POST https://{your-instance}.pulse-internal/api/pulse-api/payments/:id/chargeback/resolve
Authorization: Bearer <token>  (platform operator or automated system)
Content-Type: application/json

{
  "chargeback_id": "cb_7x9mK2pL4nQ8",
  "resolution": "denial",
  "resolution_detail": "Delivery records confirm full completion. Filer's claim is not supported by evidence.",
  "resolved_by": "pulse_engine_eval_v3",
  "partial_amount": null
}
```

On resolution, the system fires:

```json
{
  "event": "payment.chargeback_resolved",
  "payload": {
    "chargeback_id": "cb_7x9mK2pL4nQ8",
    "payment_id": "pay_3fR8kW2mN9vB",
    "resolution": "denial",
    "resolution_detail": "Delivery records confirm full completion. Filer's claim is not supported by evidence.",
    "amount_reversed": {
      "value": "0.00",
      "currency": "USD"
    },
    "resolved_at": "2026-04-13T15:00:00Z",
    "resolved_by": "pulse_engine_eval_v3"
  }
}
```

Both the filer and the counterparty receive this webhook. The chargeback record is immutable after resolution — no re-opening, no appeals through this pipeline. If a party believes the resolution was wrong, they must file a new dispute through the dispute resolution protocol (see `dispute-resolution-protocol.md`).

---

## Chargeback Reason Codes

We support six reason codes. Each maps to specific evidence requirements and evaluation heuristics.

### 1. `service_not_delivered`

The payer claims the contracted service was never delivered.

**Evidence expectations:**
- Filer should provide the task assignment or contract reference.
- Counterparty should provide delivery records, completion timestamps, and acknowledgment receipts.

**Evaluation bias:** Strong presumption toward filer if no delivery records exist. Strong presumption toward counterparty if verified delivery records show completion.

### 2. `service_not_as_described`

The payer received something, but it materially differs from what was contracted.

**Evidence expectations:**
- Filer should describe the discrepancy with specific examples.
- Counterparty should provide the original task specification and evidence that delivery matched it.

**Evaluation bias:** This is the most subjective reason code. The evaluation engine weighs it carefully and escalates to human review more often than other codes. Partial reversals are common outcomes here.

### 3. `duplicate_transaction`

The payer was charged twice (or more) for the same service.

**Evidence expectations:**
- Filer should reference the duplicate payment IDs.
- System automatically checks for payments with matching amounts, counterparties, and time proximity.

**Evaluation bias:** Heavily automated. If the system confirms a duplicate exists, auto-resolution is almost certain. We look at payment fingerprints — same amount, same corridor, same counterparty, within a configurable time window (default: 60 minutes).

### 4. `unauthorized_transaction`

The payer claims they did not authorize the payment.

**Evidence expectations:**
- Filer should describe how the unauthorized charge occurred.
- System checks authorization records, API key usage, and session logs.

**Evaluation bias:** Treated with high urgency. If authorization records are missing or API key compromise is suspected, the chargeback is fast-tracked. The counterparty's wallet may be subject to additional holds pending investigation. This reason code triggers a security review regardless of outcome.

### 5. `amount_error`

The payer was charged a different amount than agreed.

**Evidence expectations:**
- Filer should provide the expected amount and reference (quote, estimate, or contract).
- System compares the payment amount against any pre-payment quotes or estimates on file.

**Evaluation bias:** If a pre-payment quote exists and the charged amount differs, auto-resolution favors the filer. If no quote exists, this becomes harder to adjudicate and often escalates.

### 6. `fraud`

The payer believes the counterparty acted fraudulently.

**Evidence expectations:**
- Filer should provide detailed description of the suspected fraud.
- This reason code triggers an immediate security escalation.

**Evaluation bias:** Fraud chargebacks are never auto-resolved. They always go to human review, and the counterparty's account may be flagged for broader investigation. We don't take the word "fraud" lightly — filing a fraud chargeback that is determined to be frivolous will count against the filer's chargeback rate.

---

## Evidence Schema

All evidence submitted to the chargeback pipeline follows a consistent schema.

```json
{
  "type": "text | document_reference | delivery_record_id | screenshot_reference",
  "content": "<string>",
  "submitted_by": "<org_id>",
  "submitted_at": "<ISO 8601 timestamp>"
}
```

### Evidence Types

| Type | Content Format | Description |
|------|---------------|-------------|
| `text` | Free-form string, max 10,000 characters | Written explanation or narrative evidence. |
| `document_reference` | Document ID (e.g., `doc_ref_a1b2c3d4`) | Reference to a document stored in the platform's document store. The evaluation engine will retrieve and analyze the document. |
| `delivery_record_id` | Delivery record ID (e.g., `dlv_rec_44a8bc91e3`) | Reference to a delivery record in the reconciliation subsystem. The engine cross-references this against the payment's expected deliverables. |
| `screenshot_reference` | Screenshot reference ID (e.g., `scr_ref_a4e8f912bc`) | Reference to a screenshot stored in the platform's media store. Used for UI-based evidence like confirmation screens or error messages. |

### Evidence Limits

- Maximum 10 evidence items per submission.
- Maximum 5 submissions per party per chargeback.
- Total evidence per chargeback capped at 50 items.
- Text evidence capped at 10,000 characters per item.
- Document and screenshot references must point to existing assets; dangling references are rejected at submission time.

We cap evidence to prevent weaponization. In early testing, some orgs submitted hundreds of evidence items to overwhelm the evaluation engine and delay resolution. The caps are generous enough for legitimate disputes and restrictive enough to prevent abuse.

---

## Chargeback Limits and Rate Monitoring

### Per-Organization Limits

Every organization has a monthly chargeback budget:

| Org Tier | Max Chargebacks Filed / Month | Max Chargebacks Received / Month |
|----------|-------------------------------|----------------------------------|
| Standard | 25 | 50 |
| Professional | 50 | 100 |
| Enterprise | 200 | 500 |

Exceeding the filing limit results in a 48-hour cooldown before new chargebacks can be filed. Exceeding the receiving limit triggers a compliance review.

### 2% Rate Monitoring

We monitor two rates continuously:

1. **Filing Rate** = chargebacks filed / total payments made (rolling 30 days)
2. **Receiving Rate** = chargebacks received / total payments received (rolling 30 days)

If either rate exceeds 2%, the system:

1. Flags the organization in the compliance dashboard.
2. Sends a `compliance.chargeback_rate_warning` webhook to the org's registered compliance endpoint.
3. Notifies the platform operations team.
4. If the rate exceeds 5%, new payments involving that org may be held for manual review.

We picked 2% because it aligns with card network thresholds in traditional payments. In agent-to-agent commerce, the dynamics are different, but the threshold has proven reasonable in practice. Most healthy organizations sit below 0.5%.

### Repeat Offender Tracking

The system tracks chargeback patterns at the org level:

- **Serial Filers:** Orgs that file chargebacks against the same counterparty repeatedly. After 3 chargebacks against the same counterparty in 90 days, the fourth triggers mandatory human review regardless of evidence quality.
- **Frequent Losers:** Orgs whose chargebacks are denied more than 60% of the time. Triggers a compliance flag and may result in reduced chargeback limits.
- **Fraud Flag Accumulation:** Each `fraud` reason code chargeback that is denied adds a strike. Three strikes in 12 months triggers an account review.

---

## Refund Engine

Refunds are the cooperative path. Unlike chargebacks, refunds don't require adversarial evidence gathering. Either the payer, the payee, or a platform operator initiates, and the refund flows through an approval workflow.

### Initiating a Refund

```
POST https://{your-instance}.pulse-internal/api/pulse-api/payments/:id/refund
Authorization: Bearer <token>
Content-Type: application/json
Idempotency-Key: <unique-key>

{
  "refund_type": "partial",
  "amount": {
    "value": "375.00",
    "currency": "USD"
  },
  "reason_code": "service_credit",
  "reason_detail": "Client completed 30 of 50 requested analyses. Refunding for the 20 undelivered items at the per-item rate.",
  "refund_to_wallet": "wal_payer_8f3a1b_primary",
  "metadata": {
    "internal_ticket": "SUP-29401",
    "line_items_refunded": 20
  }
}
```

**Response (201 Created):**

```json
{
  "refund_id": "rfnd_4kL8mN2pQ9xB",
  "payment_id": "pay_3fR8kW2mN9vB",
  "status": "pending_approval",
  "refund_type": "partial",
  "amount": {
    "value": "375.00",
    "currency": "USD"
  },
  "reason_code": "service_credit",
  "approval_required": true,
  "approval_threshold_exceeded": false,
  "created_at": "2026-04-10T16:00:00Z"
}
```

### Refund Types

| Type | Description |
|------|-------------|
| `full` | Returns the entire payment amount. The `amount` field is ignored; the system uses the original payment amount. |
| `partial` | Returns a specified portion. The `amount` field is required and must be less than or equal to the remaining refundable amount. |

### Refund to Different Wallet

By default, refunds return to the wallet that originated the payment. The `refund_to_wallet` field allows routing to a different wallet owned by the same organization. This is useful when:

- The originating wallet has been archived.
- The org has restructured its wallet hierarchy.
- The refund should be applied to a specific project or cost center wallet.

Cross-organization refund routing is not supported. The destination wallet must belong to the same org as the original payer. We made this restriction intentionally — cross-org refund routing opens the door to money laundering patterns that are extremely difficult to detect.

### Approval Workflow

Refunds follow a tiered approval model:

| Amount | Approval |
|--------|----------|
| $0.01 - $499.99 | Auto-approved. Processed immediately. |
| $500.00 - $4,999.99 | Requires approval from org-level payment administrator. |
| $5,000.00 - $49,999.99 | Requires approval from platform payment operations. |
| $50,000.00+ | Requires dual approval: org admin + platform operations. |

Auto-approval below $500 was a deliberate trade-off. We analyzed six months of refund data and found that 94% of refunds under $500 were legitimate, and the 6% that weren't were caught by downstream reconciliation within 24 hours. The operational cost of manual review for every small refund far exceeded the fraud risk.

When approval is required:

```
POST https://{your-instance}.pulse-internal/api/pulse-api/refunds/:id/approve
Authorization: Bearer <token>
Content-Type: application/json

{
  "refund_id": "rfnd_4kL8mN2pQ9xB",
  "decision": "approved",
  "approved_by": "usr_admin_7c2b1a",
  "notes": "Confirmed partial delivery. Refund amount matches undelivered line items."
}
```

Refunds that are not approved within 72 hours are automatically escalated to the next approval tier. Refunds not approved within 7 days are auto-cancelled and the initiator is notified.

### Lifetime Total Adjustments

The system tracks the lifetime refund total for every payment. A payment's refundable amount decreases with each refund:

```
refundable_amount = original_payment_amount - sum(all_completed_refunds)
```

You cannot refund more than the original payment amount across all refunds combined. Attempting to do so returns a `422 Unprocessable Entity` with a clear error:

```json
{
  "error": "refund_exceeds_remaining",
  "message": "Requested refund of $375.00 exceeds remaining refundable amount of $250.00 for payment pay_3fR8kW2mN9vB.",
  "remaining_refundable": {
    "value": "250.00",
    "currency": "USD"
  }
}
```

This check is atomic and race-safe. Two simultaneous refund requests that would together exceed the remaining amount will not both succeed — the second will fail with this error.

---

## Refund Reason Codes

### 1. `service_credit`

A credit applied for service that was partially delivered or delivered below agreed quality standards. This is the most common reason code, accounting for roughly 45% of all refunds.

### 2. `billing_correction`

The original payment amount was incorrect due to a pricing error, miscalculated quantity, or incorrect rate application. Usually initiated by the payee (the party that was overpaid).

### 3. `duplicate_payment`

The same service was paid for twice. Unlike the `duplicate_transaction` chargeback reason code, this refund code is used when both parties agree that a duplicate occurred and want to resolve it cooperatively.

### 4. `cancellation`

The contracted service was cancelled before delivery began, or after partial delivery with mutual agreement to unwind.

### 5. `other`

A catch-all for refund reasons that don't fit the above categories. When this code is used, the `reason_detail` field is required and must be at least 50 characters. We enforce the minimum length because "other" with no explanation is useless for audit and pattern detection.

---

## Credit/Debit Memo System

Not every financial adjustment maps cleanly to a single payment. The memo system handles:

- Billing corrections that span multiple payments.
- Service credits issued outside of a specific payment context.
- Reconciliation adjustments discovered during end-of-period settlement.
- Platform-initiated adjustments (e.g., fee corrections, promotional credits).

### Creating a Memo

```
POST https://{your-instance}.pulse-internal/api/pulse-api/memos
Authorization: Bearer <token>
Content-Type: application/json
Idempotency-Key: <unique-key>

{
  "memo_type": "credit",
  "target_org_id": "org_payer_8f3a1b",
  "target_wallet_id": "wal_payer_8f3a1b_primary",
  "amount": {
    "value": "150.00",
    "currency": "USD"
  },
  "reason": "Reconciliation adjustment: three payments in March batch were processed at incorrect rate tier. Difference credited.",
  "reference_payment_ids": [
    "pay_a1b2c3d4e5",
    "pay_f6g7h8i9j0",
    "pay_k1l2m3n4o5"
  ],
  "effective_date": "2026-04-01",
  "metadata": {
    "reconciliation_batch": "recon_march_2026_final",
    "rate_correction": {
      "old_rate": "0.035",
      "new_rate": "0.028",
      "difference_per_payment": "50.00"
    }
  }
}
```

**Response (201 Created):**

```json
{
  "memo_id": "memo_8xK2mL4nP9qR",
  "memo_type": "credit",
  "status": "pending_approval",
  "target_org_id": "org_payer_8f3a1b",
  "target_wallet_id": "wal_payer_8f3a1b_primary",
  "amount": {
    "value": "150.00",
    "currency": "USD"
  },
  "created_at": "2026-04-10T18:00:00Z",
  "effective_date": "2026-04-01"
}
```

### Memo Types

| Type | Effect |
|------|--------|
| `credit` | Adds funds to the target wallet. Used for corrections in the org's favor, service credits, and promotional adjustments. |
| `debit` | Removes funds from the target wallet. Used for corrections against the org, fee adjustments, and clawbacks. Requires the wallet to have sufficient balance. |

### Wallet Adjustments

When a memo is approved and executed:

1. The target wallet balance is adjusted atomically.
2. A ledger entry is created with the memo ID as the reference.
3. The adjustment appears as a distinct line item in reconciliation reports — never blended with payment flows.

We keep memo adjustments visually and logically separate from payment flows in all reporting. This was a hard-won lesson: when adjustments are mixed into payment totals, reconciliation becomes a nightmare. Every memo adjustment is tagged with its `memo_id` and grouped separately in settlement reports.

### Memo Approval

All memos require approval regardless of amount. There are no auto-approved memos.

| Memo Type | Approval Required |
|-----------|-------------------|
| `credit` (any amount) | Platform payment operations |
| `debit` < $1,000 | Org-level payment administrator |
| `debit` >= $1,000 | Platform payment operations |

This asymmetry is intentional. Credits add money to wallets and are always platform-controlled. Small debits can be managed at the org level because they represent routine corrections. Large debits require platform oversight because they can significantly impact an org's operating balance.

### Memo Webhook

When a memo is issued (approved and executed), the system fires:

```json
{
  "event": "payment.memo_issued",
  "payload": {
    "memo_id": "memo_8xK2mL4nP9qR",
    "memo_type": "credit",
    "target_org_id": "org_payer_8f3a1b",
    "target_wallet_id": "wal_payer_8f3a1b_primary",
    "amount": {
      "value": "150.00",
      "currency": "USD"
    },
    "reason": "Reconciliation adjustment: three payments in March batch were processed at incorrect rate tier. Difference credited.",
    "reference_payment_ids": [
      "pay_a1b2c3d4e5",
      "pay_f6g7h8i9j0",
      "pay_k1l2m3n4o5"
    ],
    "effective_date": "2026-04-01",
    "issued_at": "2026-04-10T19:30:00Z"
  }
}
```

### Reconciliation Line Items

Memos generate dedicated reconciliation line items that appear in end-of-period settlement reports:

```json
{
  "line_item_type": "memo_adjustment",
  "memo_id": "memo_8xK2mL4nP9qR",
  "direction": "credit",
  "amount": {
    "value": "150.00",
    "currency": "USD"
  },
  "effective_date": "2026-04-01",
  "settlement_period": "2026-04",
  "reference_payments": ["pay_a1b2c3d4e5", "pay_f6g7h8i9j0", "pay_k1l2m3n4o5"],
  "description": "Rate tier correction — March batch"
}
```

These line items are always reported separately from payment-level refunds and chargebacks. The reconciliation engine treats them as a distinct adjustment category, which means your settlement totals will show:

```
Gross Payments Received:       $125,000.00
- Refunds Issued:              -  $3,200.00
- Chargeback Reversals:        -    $750.00
+ Credit Memos:                +    $150.00
- Debit Memos:                 -     $50.00
= Net Settlement:              $121,150.00
```

---

## Webhook Reference

All webhooks in this protocol follow the standard Pulse webhook format with HMAC-SHA256 signature verification.

| Event | Trigger | Recipients |
|-------|---------|------------|
| `payment.chargeback_filed` | Chargeback created | Counterparty |
| `payment.chargeback_evidence_submitted` | New evidence added | Both parties |
| `payment.chargeback_resolved` | Chargeback reaches final resolution | Both parties |
| `payment.refund_initiated` | Refund created (pending or auto-approved) | Payer and payee |
| `payment.refund_completed` | Refund approved and funds moved | Payer and payee |
| `payment.refund_cancelled` | Refund cancelled or rejected | Initiator |
| `payment.memo_issued` | Memo approved and executed | Target org |
| `compliance.chargeback_rate_warning` | Org exceeds 2% chargeback rate | Flagged org |

---

## Error Codes

| HTTP Status | Error Code | Description |
|------------|------------|-------------|
| `400` | `invalid_reason_code` | The provided reason code is not recognized. |
| `400` | `evidence_limit_exceeded` | Too many evidence items in a single submission. |
| `404` | `payment_not_found` | The referenced payment ID does not exist. |
| `409` | `chargeback_already_exists` | An active chargeback already exists for this payment. |
| `409` | `payment_not_eligible` | The payment is not in a state that allows chargebacks or refunds (e.g., already fully refunded). |
| `422` | `refund_exceeds_remaining` | The requested refund amount exceeds the remaining refundable balance. |
| `422` | `evidence_window_closed` | Evidence submission attempted after the window closed. |
| `422` | `wallet_insufficient_balance` | Debit memo or chargeback reversal would overdraw the target wallet. |
| `429` | `chargeback_limit_exceeded` | The org has exceeded its monthly chargeback filing limit. |

---

## Integration Notes

### Idempotency

All creation endpoints (`POST .../chargeback`, `POST .../refund`, `POST .../memos`) support idempotency keys. If you submit the same idempotency key twice, the second request returns the result of the first without creating a duplicate. Keys expire after 24 hours.

We strongly recommend using idempotency keys for all reversal operations. A duplicate refund is one of the most painful operational errors to unwind.

### Atomic Fund Movement

All fund movements in this protocol are atomic. When we say "atomic," we mean:

- The ledger debit and credit happen in the same transaction.
- The wallet balances update in the same transaction.
- The status update happens in the same transaction.
- The webhook is dispatched after the transaction commits (at-least-once delivery).

There is no intermediate state where funds have left one wallet but not arrived in another. If the transaction fails, nothing moves.

### Webhook Delivery

Webhooks are delivered with at-least-once semantics. Your endpoint may receive the same event more than once. Use the event ID for deduplication. We retry failed deliveries with exponential backoff: 1 minute, 5 minutes, 30 minutes, 2 hours, 12 hours. After 5 failed attempts, the webhook is marked as failed and appears in the webhook delivery dashboard.

### Rate Limits

| Endpoint | Rate Limit |
|----------|------------|
| `POST .../chargeback` | 10/minute per org |
| `POST .../refund` | 20/minute per org |
| `POST .../memos` | 10/minute per org |
| `POST .../evidence` | 30/minute per org |

---

## Appendix: State Machines

### Chargeback States

```
filed → evidence_window_open → evaluating → [resolved_full_reversal | resolved_partial_reversal | resolved_denial]
                                          → escalated_human_review → [resolved_full_reversal | resolved_partial_reversal | resolved_denial]
```

### Refund States

```
initiated → pending_approval → [approved → processing → completed]
                             → [rejected]
                             → [escalated → pending_approval (next tier)]
                             → [cancelled (timeout)]
```

### Memo States

```
created → pending_approval → [approved → executed]
                           → [rejected]
```

All terminal states are immutable. Once a chargeback is resolved, a refund is completed or rejected, or a memo is executed or rejected, the record cannot be modified. Corrections to incorrect resolutions must flow through new transactions (a new refund, a new memo, or a dispute filing).

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.4.0 | 2026-04-11 | Added repeat offender tracking, screenshot_reference evidence type |
| 1.3.0 | 2026-03-15 | Introduced credit/debit memo system |
| 1.2.0 | 2026-02-20 | Added refund-to-different-wallet support |
| 1.1.0 | 2026-01-10 | Expanded from 4 to 6 chargeback reason codes |
| 1.0.0 | 2025-11-01 | Initial release |

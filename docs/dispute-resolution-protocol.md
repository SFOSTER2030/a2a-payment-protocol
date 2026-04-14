# Dispute Resolution Protocol

**Protocol Version:** 2.1.0
**Last Revised:** 2026-04-12
**Status:** Production — governing all payment disputes across corridors
**Owner:** Payment Operations / Dispute Resolution Team

---

## Overview

This is the definitive specification for the five-phase dispute resolution lifecycle in the Pulse payment network. If the chargeback protocol is a scalpel — fast, targeted, limited — then this protocol is the full operating theater. Disputes handle everything chargebacks cannot: complex multi-party disagreements, subjective quality claims, contested deliverables, and cases where automated evaluation needs human judgment.

We designed this protocol around a single principle: **disputes must resolve.** Every phase has a deadline. Every deadline has a timeout action. There is no state where a dispute can sit indefinitely. The system pushes relentlessly toward resolution because unresolved disputes are poison — they freeze funds, erode trust, and create operational uncertainty for everyone involved.

The five phases are:

1. **Filing** — The aggrieved party opens a dispute with structured evidence.
2. **Counterparty Response** — The other side gets a time-bounded window to respond.
3. **Automated Assessment** — Pulse Engines analyze evidence, cross-reference delivery records, and generate a confidence-scored recommendation.
4. **Human Arbitration** — For cases the automation can't resolve with confidence, a human arbitrator reviews and decides.
5. **Resolution Enforcement** — The decision is executed atomically: funds move, records are sealed, webhooks fire.

No dispute skips phases. No dispute goes backward. No dispute re-opens after resolution. These constraints are not limitations — they are the architecture.

---

## Phase 1: Filing

### Opening a Dispute

A dispute is filed by either party to a completed payment. The payment must be in `completed` status and within the dispute eligibility window (default: 120 days from payment completion, configurable per corridor).

```
POST https://{your-instance}.pulse-internal/api/pulse-api/payments/:id/dispute
Authorization: Bearer <token>
Content-Type: application/json
Idempotency-Key: <unique-key>

{
  "reason_category": "quality_shortfall",
  "reason_detail": "Contracted for sentiment analysis of 10,000 customer reviews with 95% accuracy benchmark. Delivered analysis shows systematic misclassification of neutral reviews as positive, resulting in measured accuracy of 78%. Sample of 500 reviews manually verified by our QA team confirms the accuracy gap.",
  "evidence": [
    {
      "type": "text",
      "content": "Contract specified 95% accuracy on sentiment classification. Independent verification of 500-review sample shows 78% accuracy. Neutral-to-positive misclassification accounts for 84% of errors.",
      "submitted_by": "org_payer_8f3a1b",
      "submitted_at": "2026-04-10T10:00:00Z"
    },
    {
      "type": "document_reference",
      "content": "doc_ref_contract_7a2b3c",
      "submitted_by": "org_payer_8f3a1b",
      "submitted_at": "2026-04-10T10:00:00Z"
    },
    {
      "type": "delivery_record_id",
      "content": "dlv_rec_sentiment_batch_42",
      "submitted_by": "org_payer_8f3a1b",
      "submitted_at": "2026-04-10T10:01:00Z"
    },
    {
      "type": "document_reference",
      "content": "doc_ref_qa_report_9d4e5f",
      "submitted_by": "org_payer_8f3a1b",
      "submitted_at": "2026-04-10T10:01:00Z"
    }
  ],
  "requested_resolution": "partial_refund",
  "requested_amount": {
    "value": "2125.00",
    "currency": "USD"
  },
  "metadata": {
    "internal_ticket": "QA-7892",
    "accuracy_benchmark": "0.95",
    "measured_accuracy": "0.78"
  }
}
```

**Response (201 Created):**

```json
{
  "dispute_id": "dsp_9xM3nP5qR7sT",
  "payment_id": "pay_3fR8kW2mN9vB",
  "status": "filed",
  "phase": "counterparty_response",
  "reason_category": "quality_shortfall",
  "filer_org_id": "org_payer_8f3a1b",
  "counterparty_org_id": "org_provider_2c7d9e",
  "amount_in_dispute": {
    "value": "2125.00",
    "currency": "USD"
  },
  "original_payment_amount": {
    "value": "5000.00",
    "currency": "USD"
  },
  "counterparty_response_deadline": "2026-04-13T10:00:00Z",
  "created_at": "2026-04-10T10:00:00Z",
  "timeline": {
    "phase_1_filed_at": "2026-04-10T10:00:00Z",
    "phase_2_deadline": "2026-04-13T10:00:00Z",
    "phase_3_estimated_start": null,
    "phase_4_estimated_start": null,
    "phase_5_estimated_completion": null
  }
}
```

### Reason Categories

Six categories cover the universe of payment disputes we've observed in production:

| Category | Code | Description | Typical Outcome |
|----------|------|-------------|----------------|
| Quality Shortfall | `quality_shortfall` | Delivered work does not meet contracted quality standards. | Partial refund (most common) |
| Non-Delivery | `non_delivery` | Contracted work was never delivered, or delivery is materially incomplete. | Full refund if confirmed |
| Unauthorized Payment | `unauthorized_payment` | The paying org did not authorize this payment. | Full refund + security review |
| Billing Discrepancy | `billing_discrepancy` | The charged amount does not match the agreed price. | Refund of difference |
| Duplicate Charge | `duplicate_charge` | The same service was charged more than once. | Full refund of duplicate |
| Contractual Breach | `contractual_breach` | The counterparty violated specific terms of the service agreement beyond quality or delivery issues. | Varies widely |

`quality_shortfall` and `contractual_breach` are the two categories that most frequently require human arbitration. The others tend to have clearer evidentiary trails and resolve through automation.

### Evidence Array Structure

Evidence submitted at filing follows the same schema used across the chargeback protocol:

```json
{
  "type": "text | document_reference | delivery_record_id | screenshot_reference",
  "content": "<string>",
  "submitted_by": "<org_id>",
  "submitted_at": "<ISO 8601 timestamp>"
}
```

At filing, the filer must submit at least one evidence item. We don't require a specific type — text-only filings are valid — but filings with structured evidence (delivery records, document references) resolve faster and more favorably for the filer.

### On Filing, the System:

1. Validates the payment exists and is eligible for dispute.
2. Checks that no active dispute already exists for this payment. (One active dispute per payment at a time. After resolution, a new dispute can be filed if the eligibility window hasn't expired.)
3. Places a hold on the disputed amount in the counterparty's wallet.
4. Determines the counterparty response window based on whether the counterparty is an automated agent or a human-operated organization.
5. Fires the `payment.dispute_filed` webhook to the counterparty.
6. Fires the `payment.dispute_filed` webhook to the filer (confirmation).
7. Records the filing event in the dispute's immutable event timeline.

---

## Phase 2: Counterparty Response

### Response Windows

The counterparty gets a bounded window to respond. The window duration depends on the counterparty type:

| Counterparty Type | Response Window | Rationale |
|-------------------|----------------|-----------|
| Automated Agent | 24 hours | Agents should have immediate access to delivery records and can respond programmatically. |
| Human-Operated Org | 72 hours | Humans need time to gather evidence, consult with teams, and prepare a response. |

The system determines counterparty type from the org's registration profile. If the profile indicates mixed (both agent and human operations), the 72-hour window applies.

### Submitting a Response

```
POST https://{your-instance}.pulse-internal/api/pulse-api/payments/:id/dispute/respond
Authorization: Bearer <token>
Content-Type: application/json

{
  "dispute_id": "dsp_9xM3nP5qR7sT",
  "response_type": "contest",
  "response_detail": "We acknowledge the accuracy measurement methodology but dispute the benchmark interpretation. The contract specified 95% accuracy on a balanced dataset. The filer's QA sample over-represents edge cases that were explicitly excluded from the accuracy guarantee in Appendix B of the contract.",
  "evidence": [
    {
      "type": "document_reference",
      "content": "doc_ref_contract_appendix_b_8g9h0i",
      "submitted_by": "org_provider_2c7d9e",
      "submitted_at": "2026-04-11T14:30:00Z"
    },
    {
      "type": "text",
      "content": "Appendix B Section 3.2 specifies that accuracy benchmarks apply to reviews classified as 'clear sentiment' by the pre-filter. The filer's QA sample includes 127 reviews that the pre-filter flagged as ambiguous, which were explicitly excluded from the accuracy guarantee.",
      "submitted_by": "org_provider_2c7d9e",
      "submitted_at": "2026-04-11T14:30:00Z"
    },
    {
      "type": "delivery_record_id",
      "content": "dlv_rec_sentiment_prefilter_log_42",
      "submitted_by": "org_provider_2c7d9e",
      "submitted_at": "2026-04-11T14:31:00Z"
    }
  ],
  "proposed_resolution": "denial",
  "counter_offer_amount": null
}
```

**Valid `response_type` values:**

| Value | Effect |
|-------|--------|
| `contest` | Counterparty disputes the claim and provides evidence. |
| `accept` | Counterparty accepts the filer's requested resolution. Dispute skips to Phase 5. |
| `counter_offer` | Counterparty proposes a different resolution amount. Requires `counter_offer_amount`. |

If the counterparty submits a `counter_offer`, the filer has 24 hours to accept or reject it. If accepted, the dispute skips to Phase 5 with the counter-offer amount. If rejected (or no response), the dispute proceeds to Phase 3.

### Timeout: Auto-Resolve for Filer

If the counterparty does not respond before the deadline, the dispute auto-advances with a strong presumption favoring the filer:

1. The system records a `counterparty_timeout` event.
2. The dispute moves to Phase 3 (Automated Assessment), but the assessment engine is instructed to weight the absence of counterparty evidence heavily.
3. In practice, uncontested disputes almost always resolve in the filer's favor unless the delivery records tell a clearly different story.

We auto-advance rather than auto-resolve because even uncontested disputes benefit from the assessment engine's pattern detection. A filer who files 20 uncontested disputes in a month should trigger fraud detection regardless of whether counterparties respond.

---

## Phase 3: Automated Assessment

### How Assessment Works

Once the counterparty response window closes (or both parties indicate they're done), the Pulse Engine assessment pipeline processes the dispute.

The assessment engine performs the following steps in sequence:

**Step 1: Evidence Compilation**

All evidence from both parties is compiled into a structured dossier. The engine doesn't just look at the submitted evidence — it also pulls contextual data:

- The original payment record (amount, timestamp, corridor, payment method).
- Any pre-payment quotes or estimates on file.
- The delivery record associated with the payment (if one exists).
- Historical dispute data for both organizations.
- The chargeback history for this payment (if any chargebacks were filed and resolved).

**Step 2: Delivery Record Reconciliation**

If `delivery_record_id` evidence was submitted by either party, the engine retrieves the actual delivery records from the reconciliation subsystem and performs a structured comparison:

- Were the contracted deliverables completed?
- Do the completion timestamps fall within the agreed timeframe?
- Were acknowledgment receipts received from the payer?
- Do any quality metrics in the delivery record support or contradict the dispute claims?

This is the most powerful tool in the assessment engine's arsenal. Delivery records are system-generated and difficult to falsify. When delivery records clearly support one party, the engine's confidence is high.

**Step 3: Pattern Analysis**

The engine checks for patterns that inform the assessment:

- Has the filer filed similar disputes before? Against the same counterparty? With the same reason category?
- Has the counterparty had similar disputes filed against them?
- Does the dispute amount match known fraud patterns (round numbers, maximum-threshold amounts)?
- Is the timing suspicious (dispute filed immediately after payment, or very close to the eligibility deadline)?

**Step 4: Assessment Generation**

The engine produces a structured assessment:

```json
{
  "dispute_id": "dsp_9xM3nP5qR7sT",
  "assessment": {
    "recommended_resolution": "partial_refund",
    "recommended_amount": {
      "value": "1062.50",
      "currency": "USD"
    },
    "confidence_score": 71,
    "reasoning": [
      "Delivery records confirm all 10,000 reviews were processed and delivered.",
      "Filer's accuracy measurement methodology is sound, but includes reviews flagged as ambiguous by the pre-filter.",
      "Contract Appendix B does exclude ambiguous reviews from accuracy guarantee.",
      "Excluding ambiguous reviews, accuracy on clear-sentiment reviews is 89% — still below the 95% benchmark.",
      "A partial refund proportional to the accuracy gap (89% vs 95%) is recommended.",
      "Counterparty's defense partially succeeds: the gap is smaller than filer claims, but still exists."
    ],
    "evidence_weight": {
      "filer_evidence_strength": "strong",
      "counterparty_evidence_strength": "moderate",
      "delivery_records_conclusive": false,
      "contract_terms_clear": true
    },
    "auto_resolve_eligible": false,
    "escalation_reason": "confidence_below_threshold"
  }
}
```

### Auto-Resolution vs. Escalation

The engine uses the confidence score to decide whether to auto-resolve or escalate:

| Confidence Score | Action |
|-----------------|--------|
| 90-100 | Auto-resolve. The evidence clearly supports one outcome. |
| 75-89 | Auto-resolve with notation. Clear enough for automation, but the decision is flagged for periodic quality review. |
| 50-74 | Escalate to Phase 4 (Human Arbitration). The evidence is ambiguous or contradictory. |
| 0-49 | Escalate to Phase 4 with priority flag. The engine cannot make a meaningful recommendation. |

In the example above, the confidence score of 71 falls in the escalation range. The dispute advances to Phase 4.

When the engine auto-resolves (confidence >= 75), it:

1. Records the assessment and resolution in the dispute record.
2. Fires the `payment.dispute_assessed` webhook to both parties with the assessment details.
3. Immediately advances to Phase 5 (Resolution Enforcement).

When the engine escalates, it:

1. Records the assessment (including the recommended resolution) in the dispute record.
2. Fires the `payment.dispute_escalated` webhook to both parties.
3. Routes the dispute to the Human Arbitration queue.

---

## Phase 4: Human Arbitration

### Property Dispatcher Routing

Escalated disputes are routed to human arbitrators through the Property Dispatcher — a workload distribution system that matches disputes to qualified reviewers based on:

- **Dispute amount:** Higher-value disputes are routed to senior arbitrators.
- **Reason category:** Some arbitrators specialize in quality disputes, others in contractual interpretation.
- **Corridor familiarity:** Arbitrators who understand the specific agent corridor (e.g., data processing, content generation, financial analysis) are preferred.
- **Current workload:** The dispatcher balances load across the arbitrator pool to meet SLAs.

Disputes are never assigned to an arbitrator who has a conflict of interest (e.g., the arbitrator's org is a customer of either party). The system checks for conflicts automatically.

### Arbitrator Evidence View

The arbitrator receives a structured view of the dispute:

1. **Summary panel:** Dispute details, amounts, reason category, timeline.
2. **Filer's case:** All evidence submitted by the filer, chronologically ordered.
3. **Counterparty's case:** All evidence submitted by the counterparty, chronologically ordered.
4. **Assessment recommendation:** The Pulse Engine's recommended resolution with reasoning.
5. **Contextual data:** Payment history between the parties, dispute history, chargeback rates.
6. **Delivery records:** If applicable, the full delivery record with completion metrics.

The arbitrator can request additional evidence from either party. This extends the Phase 4 window by 24 hours per request, up to a maximum of two requests (total extension: 48 hours).

### Rendering a Decision

```
POST https://{your-instance}.pulse-internal/api/pulse-api/payments/:id/dispute/arbitrate
Authorization: Bearer <token>
Content-Type: application/json

{
  "dispute_id": "dsp_9xM3nP5qR7sT",
  "decision": "partial_refund",
  "decision_amount": {
    "value": "1250.00",
    "currency": "USD"
  },
  "rationale": "Both parties presented credible evidence. The contract does exclude ambiguous reviews from the accuracy benchmark, which reduces the scope of the quality shortfall. However, even on clear-sentiment reviews, accuracy was 89% versus the 95% benchmark. The 6% gap on clear reviews represents a meaningful quality shortfall. A refund of 25% of the payment amount reflects the proportional impact of the accuracy gap on the usable output.",
  "arbitrated_by": "arb_usr_4k7m2n",
  "evidence_requests_made": 0
}
```

### Phase 4 Deadlines

| Event | Deadline | Timeout Action |
|-------|----------|----------------|
| Arbitrator assigned | 4 hours from escalation | Re-route to next available arbitrator |
| Initial review completed | 24 hours from assignment | Escalate to senior arbitrator |
| Decision rendered | 48 hours from assignment | Escalate to fund administrator |
| Fund administrator decision | 7 days from original escalation | Auto-refund to filer |

The 7-day auto-refund is our nuclear option. If the entire arbitration pipeline fails to produce a decision within 7 days, the system defaults to refunding the filer. We chose filer-favoring because:

1. Funds are already held from the counterparty's wallet.
2. A counterparty who has been responsive throughout the process is unlikely to reach this point.
3. The 7-day timeout almost always indicates a systemic problem (arbitrator shortage, holiday period) rather than a close case.

In practice, the 7-day timeout fires fewer than 0.1% of the time. Most disputes are arbitrated within 36 hours of escalation.

### Fund Administrator Escalation

If the assigned arbitrator does not render a decision within 48 hours, the dispute escalates to a fund administrator — a senior role with broader authority. The fund administrator:

- Can review the arbitrator's notes (if any were started).
- Has access to the same evidence view.
- Must render a decision within the remaining time before the 7-day auto-refund triggers.
- Can override the Pulse Engine's recommendation with documented rationale.

---

## Phase 5: Resolution Enforcement

### Atomic Fund Movement

When a dispute reaches resolution (whether by auto-resolution in Phase 3, arbitrator decision in Phase 4, or timeout auto-refund), the system enforces the decision atomically:

1. **Fund movement:** If the resolution involves a refund (full or partial), the held amount (or the decided portion) is moved from the counterparty's wallet to the filer's wallet in a single atomic transaction.
2. **Hold release:** Any remaining held amount is released back to the counterparty's available balance.
3. **Ledger entries:** Both wallets receive ledger entries referencing the dispute ID.
4. **Status finalization:** The dispute status moves to `resolved` with the specific resolution type.

The fund movement and status update happen in the same database transaction. There is no window where funds are in flight.

### Immutable Dispute Record

Once resolved, the dispute record is sealed:

- No modifications to any field.
- No additional evidence can be submitted.
- No re-opening of the dispute.
- No appeals.

We understand the "no appeals" policy is controversial. Here's why we enforce it: appeals create second-order disputes about the first dispute. They double the operational overhead, keep funds in limbo longer, and in our analysis of traditional payment dispute systems, appeals overturn fewer than 3% of decisions. The cost-benefit doesn't justify the complexity.

If a party genuinely believes a resolution was wrong, their recourse is:

1. File a new dispute for the same payment (if still within the eligibility window) with new evidence that was not available during the original dispute.
2. Escalate through their platform account manager for an offline review.
3. Pursue resolution through external legal channels.

Option 1 is the intended path and covers most legitimate cases. The system prevents re-filing with identical evidence — new evidence is required.

### Webhooks to Both Parties

On resolution, both parties receive webhooks:

```json
{
  "event": "payment.dispute_resolved",
  "payload": {
    "dispute_id": "dsp_9xM3nP5qR7sT",
    "payment_id": "pay_3fR8kW2mN9vB",
    "resolution": "partial_refund",
    "resolution_amount": {
      "value": "1250.00",
      "currency": "USD"
    },
    "resolution_source": "human_arbitration",
    "rationale_summary": "Quality shortfall confirmed on clear-sentiment subset. 25% refund proportional to accuracy gap.",
    "filer_wallet_credited": "wal_payer_8f3a1b_primary",
    "counterparty_wallet_debited": "wal_provider_2c7d9e_ops",
    "resolved_at": "2026-04-12T16:45:00Z",
    "resolved_by": "arb_usr_4k7m2n",
    "phase_resolved_in": 4
  }
}
```

---

## Timeline Summary

This table is the operational bible. Every deadline and timeout action at a glance.

| Phase | Event | Deadline | Timeout Action |
|-------|-------|----------|----------------|
| 1 - Filing | Dispute filed | — | — |
| 1 - Filing | Payment eligibility check | Immediate | Reject if outside window |
| 1 - Filing | Fund hold placed | Immediate | Reject dispute if hold fails |
| 2 - Response | Counterparty response (agent) | 24h from filing | Auto-advance to Phase 3 |
| 2 - Response | Counterparty response (human) | 72h from filing | Auto-advance to Phase 3 |
| 2 - Response | Counter-offer acceptance by filer | 24h from counter-offer | Auto-reject counter-offer, advance to Phase 3 |
| 3 - Assessment | Pulse Engine assessment | 2h from Phase 2 close | Escalate directly to Phase 4 |
| 3 - Assessment | Auto-resolution (confidence >= 75) | Immediate | — |
| 3 - Assessment | Escalation (confidence < 75) | Immediate | — |
| 4 - Arbitration | Arbitrator assignment | 4h from escalation | Re-route to next arbitrator |
| 4 - Arbitration | Arbitrator decision | 48h from assignment | Escalate to fund administrator |
| 4 - Arbitration | Additional evidence request response | 24h per request (max 2) | Proceed without additional evidence |
| 4 - Arbitration | Fund administrator decision | 7 days from Phase 4 start | Auto-refund to filer |
| 5 - Enforcement | Fund movement | Immediate on decision | — |
| 5 - Enforcement | Webhooks dispatched | Within 60s of resolution | Retry with exponential backoff |

---

## API Routes

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `https://{your-instance}.pulse-internal/api/pulse-api/payments/:id/dispute` | File a new dispute against a payment. |
| `POST` | `https://{your-instance}.pulse-internal/api/pulse-api/payments/:id/dispute/respond` | Submit counterparty response with evidence. |
| `POST` | `https://{your-instance}.pulse-internal/api/pulse-api/payments/:id/dispute/arbitrate` | Render an arbitration decision (arbitrator/fund admin only). |
| `GET` | `https://{your-instance}.pulse-internal/api/pulse-api/payments/:id/dispute` | Retrieve the current state of a dispute for a payment. |
| `GET` | `https://{your-instance}.pulse-internal/api/pulse-api/disputes/:dispute_id/events` | Retrieve the full event timeline for a dispute. |

All routes require Bearer token authentication. Write operations (`POST`) require the caller to have the appropriate role (filer, counterparty, or arbitrator) for the specific dispute.

---

## Webhook Events

| Event | Trigger | Recipients | Phase |
|-------|---------|------------|-------|
| `payment.dispute_filed` | Dispute created successfully | Both parties | 1 |
| `payment.dispute_response_received` | Counterparty submits response | Filer | 2 |
| `payment.dispute_assessed` | Pulse Engine completes assessment | Both parties | 3 |
| `payment.dispute_escalated` | Dispute escalated to human arbitration | Both parties | 3→4 |
| `payment.dispute_resolved` | Dispute reaches final resolution | Both parties | 5 |
| `payment.dispute_timeout` | A phase deadline expired without action | Both parties | Any |

All webhooks include the `dispute_id`, `payment_id`, `phase`, and `status` in their payload. Webhooks are delivered with at-least-once semantics. Use the `event_id` field for deduplication.

---

## Impact on Other Agents

Disputes don't exist in a vacuum. When dispute volume or patterns change, other Pulse Engines adjust their behavior.

### Authorizer: Policy Tightening

The Authorizer agent monitors dispute rates per org and per corridor. When an org's dispute rate exceeds thresholds, the Authorizer automatically tightens payment policies:

| Dispute Rate (30-day rolling) | Authorizer Action |
|-------------------------------|-------------------|
| < 2% | No action. Normal operations. |
| 2% - 5% | Warning flag. New payments from/to this org are logged with elevated monitoring. |
| > 5% | Automatic tightening. New payments involving this org require pre-authorization with a 15-minute hold for review. |
| > 10% | Suspension recommendation. The Authorizer recommends suspending new payment initiation for the org pending compliance review. (Recommendation only — suspension requires human approval.) |

The Authorizer treats filed disputes and received disputes separately. An org can have a low filing rate but a high receiving rate, which indicates they're a problematic provider, not a serial complainer.

Policy tightening is proportional and reversible. When the dispute rate drops back below thresholds (measured over the subsequent 30-day window), policies relax automatically. We don't punish orgs permanently for a bad month.

### Reconciliation: Dispute Rate as Detection Category

The Reconciliation engine maintains seven anomaly detection categories for identifying patterns that need human attention. Disputes add an eighth:

1. Amount anomalies
2. Frequency anomalies
3. Timing anomalies
4. Corridor anomalies
5. Counterparty concentration
6. Settlement discrepancies
7. Delivery completion gaps
8. **Dispute rate anomalies** (added by this protocol)

The `dispute_rate` detection category triggers when:

- An org's dispute rate changes by more than 2x in a 7-day period.
- A specific corridor's dispute rate exceeds the network-wide average by more than 3x.
- A specific counterparty pair generates more than 5 disputes in 30 days.
- The ratio of disputes to chargebacks for an org deviates significantly from the network norm (indicating possible channel shopping — filing disputes instead of chargebacks or vice versa to exploit different resolution dynamics).

When triggered, the Reconciliation engine adds the anomaly to its daily report and fires a `reconciliation.anomaly_detected` webhook with `category: "dispute_rate"`.

### Sovereign Intelligence: Pattern Learning

The Sovereign Intelligence engine — the system that governs cross-agent coordination and network-level optimization — consumes dispute resolution data to learn patterns:

- **Counterparty reliability scoring:** Dispute outcomes feed into reliability scores that inform routing decisions. An org that consistently loses disputes sees its reliability score decrease, which affects whether other agents choose to transact with them.
- **Pricing signal extraction:** When disputes resolve with partial refunds, the refund proportion becomes a signal about fair pricing for that type of service. If 40% of quality disputes in a corridor resolve with 20-30% refunds, the Sovereign Intelligence engine adjusts its pricing guidance for that corridor.
- **Fraud pattern detection:** Cross-org dispute patterns (e.g., a ring of orgs filing disputes against each other to extract funds) are detected through graph analysis of dispute relationships.
- **Seasonal adjustment:** Some corridors see dispute spikes during specific periods (end of quarter, budget cycles). The Sovereign Intelligence engine learns these patterns and pre-adjusts arbitrator staffing recommendations.

None of these pattern-learning outputs directly affect individual dispute resolutions. They operate at the network level, influencing policies, routing, and resource allocation. We deliberately firewall individual dispute decisions from aggregate pattern learning to prevent feedback loops.

---

## Data Model

### Dispute Record

The dispute record is the central data structure. Every dispute has exactly one record, and it accumulates state as the dispute progresses through phases.

| Field | Type | Description |
|-------|------|-------------|
| `dispute_id` | string | Unique identifier. Format: `dsp_` + 12 alphanumeric characters. |
| `payment_id` | string | The payment being disputed. |
| `status` | enum | One of: `filed`, `awaiting_response`, `assessing`, `arbitrating`, `resolved`, `resolved_timeout`. |
| `phase` | integer | Current phase (1-5). |
| `reason_category` | enum | One of the six reason categories. |
| `reason_detail` | string | Free-text description from the filer. Max 5,000 characters. |
| `filer_org_id` | string | The organization that filed the dispute. |
| `counterparty_org_id` | string | The organization being disputed against. |
| `amount_in_dispute` | money | The amount the filer is requesting back. |
| `original_payment_amount` | money | The full amount of the original payment. |
| `resolution` | enum (nullable) | One of: `full_refund`, `partial_refund`, `denial`, `withdrawn`. Null until resolved. |
| `resolution_amount` | money (nullable) | The amount refunded. Null until resolved. Zero for denial. |
| `resolution_source` | enum (nullable) | One of: `auto_assessment`, `human_arbitration`, `counterparty_accepted`, `timeout_auto_refund`, `filer_withdrawal`. |
| `resolution_rationale` | string (nullable) | Explanation of the decision. |
| `resolved_by` | string (nullable) | Identifier of the entity that resolved (engine version, arbitrator user ID, or `system_timeout`). |
| `counterparty_response_type` | enum (nullable) | One of: `contest`, `accept`, `counter_offer`, `no_response`. |
| `counterparty_response_deadline` | timestamp | When the counterparty response window closes. |
| `assessment_confidence_score` | integer (nullable) | The Pulse Engine's confidence score (0-100). |
| `assessment_recommended_resolution` | enum (nullable) | What the engine recommended. |
| `arbitrator_id` | string (nullable) | The assigned arbitrator, if escalated. |
| `fund_hold_id` | string | Reference to the fund hold placed at filing. |
| `created_at` | timestamp | When the dispute was filed. |
| `updated_at` | timestamp | Last modification timestamp. |
| `resolved_at` | timestamp (nullable) | When the dispute was resolved. |
| `metadata` | object | Arbitrary key-value pairs from the filer. |

### Dispute Events Timeline

Every state change, evidence submission, and system action generates an event. The events timeline is the authoritative audit trail.

| Field | Type | Description |
|-------|------|-------------|
| `event_id` | string | Unique event identifier. |
| `dispute_id` | string | Parent dispute. |
| `event_type` | enum | See event types below. |
| `phase` | integer | Phase when the event occurred. |
| `actor` | string | Who caused the event (org ID, user ID, system identifier). |
| `detail` | object | Event-specific payload. |
| `created_at` | timestamp | When the event occurred. |

**Event types:**

| Event Type | Description |
|-----------|-------------|
| `dispute_filed` | Dispute was created. |
| `fund_hold_placed` | Funds were held in counterparty wallet. |
| `evidence_submitted` | Evidence was added by either party. |
| `counterparty_responded` | Counterparty submitted their formal response. |
| `counterparty_timeout` | Counterparty response window expired without response. |
| `counter_offer_submitted` | Counterparty proposed alternative resolution. |
| `counter_offer_accepted` | Filer accepted the counter-offer. |
| `counter_offer_rejected` | Filer rejected the counter-offer. |
| `counter_offer_expired` | Counter-offer acceptance window expired. |
| `assessment_started` | Pulse Engine began evaluation. |
| `assessment_completed` | Pulse Engine produced a recommendation. |
| `auto_resolved` | Engine auto-resolved the dispute. |
| `escalated_to_arbitration` | Dispute sent to human review. |
| `arbitrator_assigned` | An arbitrator was assigned. |
| `arbitrator_reassigned` | Dispute re-routed to a different arbitrator. |
| `additional_evidence_requested` | Arbitrator requested more evidence. |
| `additional_evidence_submitted` | Party submitted requested evidence. |
| `additional_evidence_deadline_expired` | Evidence request window expired. |
| `arbitration_decision_rendered` | Arbitrator made a decision. |
| `escalated_to_fund_admin` | Arbitrator timed out, fund admin takes over. |
| `fund_admin_decision_rendered` | Fund admin made a decision. |
| `timeout_auto_refund` | 7-day deadline expired, auto-refund triggered. |
| `fund_movement_executed` | Funds moved between wallets. |
| `fund_hold_released` | Remaining held funds released. |
| `dispute_resolved` | Terminal event. Dispute is sealed. |
| `webhook_dispatched` | Webhook sent to a party. |
| `webhook_delivery_failed` | Webhook delivery failed (will retry). |

The events timeline is append-only. No events are ever modified or deleted. This is the ground truth for any audit or compliance review.

---

## Error Codes

| HTTP Status | Error Code | Description |
|------------|------------|-------------|
| `400` | `invalid_reason_category` | Unrecognized reason category. |
| `400` | `insufficient_evidence` | Filing requires at least one evidence item. |
| `400` | `invalid_response_type` | Unrecognized response type. |
| `403` | `not_dispute_party` | Caller is not the filer or counterparty for this dispute. |
| `403` | `not_authorized_arbitrator` | Caller is not assigned as arbitrator for this dispute. |
| `404` | `payment_not_found` | Referenced payment does not exist. |
| `404` | `dispute_not_found` | Referenced dispute does not exist. |
| `409` | `active_dispute_exists` | An active dispute already exists for this payment. |
| `409` | `payment_not_eligible` | Payment is not in a disputable state. |
| `409` | `dispute_not_in_expected_phase` | The dispute is not in the phase required for this action. |
| `422` | `amount_exceeds_payment` | Disputed amount exceeds the original payment amount. |
| `422` | `response_window_closed` | Counterparty response window has expired. |
| `422` | `duplicate_evidence` | Identical evidence was already submitted. |
| `429` | `dispute_rate_limit` | Org has exceeded dispute filing rate limit. |

---

## Edge Cases and Operational Notes

### Concurrent Chargeback and Dispute

A payment cannot have both an active chargeback and an active dispute simultaneously. If a chargeback is active when a dispute is filed, the dispute is rejected with `active_chargeback_exists`. If a dispute is active when a chargeback is filed, the chargeback is rejected with `active_dispute_exists`. This prevents double-dipping.

After a chargeback resolves, a dispute can be filed (and vice versa), as long as the payment is still within the eligibility window. However, the second filing's assessment will heavily consider the outcome of the first. Filing a dispute after losing a chargeback on the same payment is not prohibited, but it's an uphill battle.

### Withdrawal

A filer can withdraw a dispute at any point before Phase 5:

```
POST https://{your-instance}.pulse-internal/api/pulse-api/payments/:id/dispute/withdraw
Authorization: Bearer <token>
Content-Type: application/json

{
  "dispute_id": "dsp_9xM3nP5qR7sT",
  "withdrawal_reason": "Issue resolved directly with counterparty outside of dispute process."
}
```

Withdrawal:
- Immediately releases the fund hold.
- Fires a `payment.dispute_resolved` webhook with `resolution: "withdrawn"`.
- Seals the dispute record.
- Counts toward the filer's dispute history (withdrawals are not free — they still affect dispute rate metrics, though with lower weight than losses).

### Multi-Currency Disputes

When the original payment and the filer's wallet are in different currencies, the fund movement at resolution uses the exchange rate locked at the time of the original fund hold (Phase 1). We don't use the rate at resolution time because that would create an incentive to delay or expedite disputes based on exchange rate movements.

### Partial Payment Recovery

If the counterparty's wallet has insufficient funds to cover a full refund at resolution time (e.g., the counterparty has withdrawn funds during the dispute), the system:

1. Moves whatever is available from the held amount. (The hold should cover this, but holds can be reduced by higher-priority claims like regulatory freezes.)
2. Creates a `recovery_pending` ledger entry for the shortfall.
3. Applies future incoming payments to the counterparty's wallet toward the recovery amount.
4. Notifies the filer that recovery is in progress.

Full recovery is guaranteed by the platform, but may take time if the counterparty's account is underfunded.

---

## Rate Limits

| Endpoint | Rate Limit |
|----------|------------|
| `POST .../dispute` | 5/minute per org |
| `POST .../dispute/respond` | 10/minute per org |
| `POST .../dispute/arbitrate` | 20/minute per arbitrator |
| `GET .../dispute` | 60/minute per org |
| `GET .../disputes/:id/events` | 30/minute per org |

---

## Monitoring and Observability

### Key Metrics We Track

- **Dispute volume:** Total disputes filed per day, per corridor, per org.
- **Resolution time:** P50, P90, P99 time from filing to resolution.
- **Phase duration:** Time spent in each phase, broken down by reason category.
- **Auto-resolution rate:** Percentage of disputes resolved in Phase 3 without human intervention.
- **Arbitrator utilization:** Queue depth and decision throughput per arbitrator.
- **Timeout rate:** Percentage of disputes that hit any timeout trigger.
- **Filer win rate:** Percentage of disputes resolved in the filer's favor, segmented by reason category.
- **Appeal-via-refiling rate:** Percentage of resolved disputes followed by a new dispute on the same payment.

### Alerting Thresholds

| Metric | Warning | Critical |
|--------|---------|----------|
| Dispute volume (daily) | > 2x 30-day average | > 5x 30-day average |
| Phase 4 queue depth | > 50 unassigned | > 100 unassigned |
| Arbitrator decision time (P90) | > 36 hours | > 44 hours |
| Timeout auto-refund rate | > 0.5% | > 2% |
| Auto-resolution rate drop | < 60% (30-day rolling) | < 40% (30-day rolling) |

---

## Integration Checklist

For teams integrating with the dispute system, here's what you need:

1. **Webhook endpoints registered** for all six dispute events.
2. **Idempotency key generation** for all dispute-filing and response calls.
3. **Evidence preparation pipeline** — your system should be able to pull delivery records, contract references, and quality metrics programmatically when a dispute is filed against you.
4. **Response automation** for straightforward cases — if your delivery records clearly show full completion, an automated `contest` response with delivery record evidence can be generated within the 24-hour agent window.
5. **Monitoring dashboard** tracking your dispute filing rate, receiving rate, and win/loss ratio.
6. **Escalation workflow** for disputes that require human judgment on your side (quality claims, contractual interpretation).
7. **Financial reconciliation integration** — dispute resolutions (refunds, holds, releases) need to flow into your accounting system.

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 2.1.0 | 2026-04-12 | Added counter-offer flow, multi-currency handling, partial payment recovery |
| 2.0.0 | 2026-03-01 | Complete rewrite. Five-phase model replaces three-phase. Added Sovereign Intelligence integration. |
| 1.2.0 | 2026-01-20 | Added `contractual_breach` reason category. Extended eligibility window to 120 days. |
| 1.1.0 | 2025-12-05 | Introduced automated assessment engine. Previously all disputes went to human review. |
| 1.0.0 | 2025-10-15 | Initial release. Three-phase model with manual review only. |

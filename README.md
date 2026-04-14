<p align="center">
  <strong>A2A PAYMENT PROTOCOL</strong>
</p>

<h1 align="center">Agent-to-Agent Payment Infrastructure</h1>

<p align="center">
  Production-grade specification for secure, verifiable, and compliant payment infrastructure<br>between autonomous AI agents. Architecture is public. Implementation is proprietary.<br>Every endpoint routes through the Pulse API.
</p>

<p align="center">
  <code>v1.7.0</code> · <code>49 Agents</code> · <code>50 API Routes</code> · <code>98 Tables</code> · <code>76 Inter-Agent Routes</code>
</p>

<p align="center">
  <a href="docs/quickstart.md">Quickstart</a> · <a href="spec/openapi.yaml">OpenAPI Spec</a> · <a href="docs/v1.6.5-validation-report.md">Validation Report</a> · <a href="docs/architecture-overview.md">Architecture</a> · <a href="docs/changelog.md">Changelog</a>
</p>

<p align="center">
  <a href="https://a2a.tfsfventures.com">Read the White Paper →</a>
</p>

---

## Overview

This repository is the complete technical specification for agent-to-agent payment infrastructure in production. It defines how autonomous AI agents authorize, settle, dispute, reverse, and reconcile payments between each other — with spending policy enforcement, conditional escrow, 5-phase dispute resolution, chargeback pipelines, and daily automated anomaly detection.

A [peer-reviewed SoK paper](https://arxiv.org/abs/2604.03733) published April 2026 confirmed that agent-to-agent payments represent an unsolved infrastructure gap across a four-stage lifecycle: discovery, authorization, execution, and accounting. Every existing approach — card networks adapting consumer checkout, blockchain experiments, AI orchestration platforms — fails at one or more stages. This protocol addresses all four in a single system.

This repository contains the **specification and architecture reference**. It does not contain the implementation. The implementation is proprietary and runs inside the [Pulse AI platform](https://tfsfventures.com). All endpoints route through the Pulse API. The spec is the contract. The infrastructure behind it is ours.

---

## The Problem

| Gap | Impact |
|-----|--------|
| No authorization model for autonomous agent spending | Humans must approve every transaction — agents cannot operate financially independent |
| No escrow primitive for multi-step agent work | When Agent A pays Agent B for work, there is no mechanism to hold funds until delivery is verified |
| No dispute resolution for agent-to-agent payments | When work is paid for but never delivered, there is no recourse and no reversal path |
| No reconciliation protocol for agent transactions | At 4,500+ autonomous transactions per week across a fund, manual auditing is impossible |
| No compliance-aware payment routing between agents | Agents accidentally violate regulations across jurisdictions without pre-transaction screening |

Visa, Mastercard, and Google are adapting consumer checkout for agent-initiated purchases. That solves agent-to-human commerce. It does not solve agent-to-agent commerce within enterprise systems — autonomous agents paying each other for services, governed by machine-enforceable policies, with conditional escrow, compliance scanning, and automated reconciliation. That is what this protocol defines.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         PULSE API GATEWAY                            │
│                                                                      │
│  50 routes · SHA-256 key auth · IP whitelist · 29 permissions        │
│  Rate limiting · Idempotency enforcement · HMAC-SHA256 webhooks      │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                    PAYMENT AGENT LAYER                         │  │
│  │                                                                │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │  │
│  │  │ TRANSACTION  │  │ SETTLEMENT   │  │ RECONCIL-    │        │  │
│  │  │ AUTHORIZER   │→ │ EXECUTOR     │→ │ IATION       │        │  │
│  │  │ #43          │  │ #44          │  │ AUDITOR #45  │        │  │
│  │  │              │  │              │  │              │        │  │
│  │  │ 10-step      │  │ Instant      │  │ 8 detection  │        │  │
│  │  │ pipeline     │  │ Escrow       │  │ categories   │        │  │
│  │  │ 12 denial    │  │ External     │  │ Daily auto   │        │  │
│  │  │ codes        │  │ Webhooks     │  │ AI anomaly   │        │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘        │  │
│  │                                                                │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │  │
│  │  │ DISPUTE      │  │ PAYMENT      │  │ SETTLEMENT   │        │  │
│  │  │ RESOLUTION   │  │ EXCEPTION    │  │ OPERATIONS   │        │  │
│  │  │ MANAGER #46  │  │ HANDLER #47  │  │ #48          │        │  │
│  │  │              │  │              │  │              │        │  │
│  │  │ 5-phase      │  │ Chargebacks  │  │ Partial      │        │  │
│  │  │ lifecycle    │  │ Refunds      │  │ Split/Batch  │        │  │
│  │  │ Auto-assess  │  │ Holds        │  │ Fees         │        │  │
│  │  │ Arbitration  │  │ Dead letter  │  │ FX           │        │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘        │  │
│  │                                                                │  │
│  │  ┌──────────────┐                                             │  │
│  │  │ COMPLIANCE   │   76 inter-agent routes                     │  │
│  │  │ REPORTER #49 │   22 webhook event types                    │  │
│  │  │              │   8 scheduled jobs                          │  │
│  │  │ Statements   │   Daily automated reconciliation            │  │
│  │  │ Audit export │                                             │  │
│  │  │ Analytics    │                                             │  │
│  │  └──────────────┘                                             │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                      CORE PLATFORM                             │  │
│  │                                                                │  │
│  │  49 production agents · 98 database tables (all with RLS)      │  │
│  │  74 service endpoints · Multi-tenant org isolation              │  │
│  │  Sovereign Intelligence Layer · Predictive Compliance           │  │
│  │  Autonomous scheduling · Property hub-and-spoke                 │  │
│  └────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

Full specification: [docs/architecture-overview.md](docs/architecture-overview.md)

---

## Authorization Pipeline

Every payment request passes through a 10-step authorization pipeline before any money moves. Active payment holds are checked before step 1 — if a hold exists on either party, the transaction is denied immediately.

```
payment_request
│
├─ HOLD CHECK — active holds on agent, org, or fund block immediately
│
├─ 1. Load spending policy (agent-specific → org default → fund default → deny)
├─ 2. Validate amount ≤ max_per_transaction
├─ 3. Validate daily_spend + amount ≤ max_daily (rolling 24h, atomic)
├─ 4. Validate monthly_spend + amount ≤ max_monthly (rolling 30d, atomic)
├─ 5. Check counterparty (blocked list takes precedence over approved list)
├─ 6. Check transaction category against allowed_categories
├─ 7. Check wallet: available_balance ≥ amount
├─ 8. If amount > require_human_above → ESCALATE to human via Property Dispatcher
├─ 9. If compliance_precheck enabled → scan configured jurisdictions
└─ 10. Decision
        │
   ┌────┴────┐
   ▼         ▼
AUTHORIZE    DENY (+ reason_code + audit record + frozen policy snapshot)
```

**12 denial reason codes:** `no_policy` · `policy_exceeded` · `budget_exceeded` · `counterparty_blocked` · `counterparty_not_approved` · `category_restricted` · `insufficient_balance` · `compliance_fail` · `human_required` · `human_denied` · `system_error` · `payment_hold`

Concurrent authorization uses advisory locks on agent_id + org_id. Daily and monthly spend calculated as atomic SUM across all authorized, executing, and settled transactions within rolling windows. Policy snapshots frozen into the authorization record at decision time — the audit trail shows exactly what rules were in effect, even if the policy changes later.

Full specification: [docs/authorization-protocol.md](docs/authorization-protocol.md) · [docs/spending-policy-schema.md](docs/spending-policy-schema.md)

---

## Settlement

Three settlement modes exist because three real-world scenarios demand them:

| Mode | Use Case | Mechanism |
|------|----------|-----------|
| **Instant Atomic** | Trusted agents, same org, straightforward service fees | Atomic debit/credit in single database transaction. Both wallets update simultaneously. HMAC-SHA256 webhooks to both parties. |
| **Conditional Escrow** | Cross-org transactions, delivery verification required | Funds held in sender's held_balance → verification agent or human confirms delivery → released to counterparty. Timeout → auto-refund. Dispute → frozen for human resolution. |
| **External** | Real money settlement between organizations | Production payment rails with authorization, fraud screening, capture, clearing, settlement, and reconciliation. |

### Escrow State Machine — 5 States, 6 Transitions

```
                     ┌──────────┐
                     │   HELD   │
                     └────┬─────┘
                          │
           ┌──────────────┼──────────────┐
           │              │              │
           ▼              ▼              ▼
     ┌───────────┐  ┌─────────┐  ┌───────────┐
     │ RELEASED  │  │ EXPIRED │  │ DISPUTED  │
     │           │  │         │  │           │
     │ funds →   │  │    │    │  │  ┌────┐   │
     │ counter-  │  │    ▼    │  │  ▼    ▼   │
     │ party     │  │REFUNDED │  │ REL. REF. │
     └───────────┘  └─────────┘  └───────────┘
```

| From | To | Trigger |
|------|----|---------|
| HELD | RELEASED | Verification confirms delivery |
| HELD | EXPIRED | Timeout reached, then auto-refunds |
| HELD | DISPUTED | Either party files dispute |
| EXPIRED | REFUNDED | Automatic — funds return to sender |
| DISPUTED | RELEASED | Human arbitrator decides to release |
| DISPUTED | REFUNDED | Human arbitrator decides to refund |

Seven escrow race conditions documented and fixed during 50-concurrent-actor load testing. SELECT FOR UPDATE prevents concurrent state transitions. The `available_balance + held_balance = total_funds` invariant is maintained through every state change within atomic database transactions.

Full specification: [docs/settlement-protocol.md](docs/settlement-protocol.md) · [docs/escrow-lifecycle.md](docs/escrow-lifecycle.md) · [docs/escrow-race-conditions.md](docs/escrow-race-conditions.md)

---

## Dispute Resolution

Disputes are a first-class workflow with their own 5-phase lifecycle — not a status flag on an escrow. Every phase has a deadline. Every deadline has a timeout action. No dispute sits indefinitely.

| Phase | What Happens | Deadline | Timeout Action |
|-------|-------------|----------|----------------|
| **Filing** | Either party files with reason category and structured evidence | — | — |
| **Counterparty Response** | Counterparty submits delivery records, output hashes, timestamps | 24h (agent) / 72h (human) | Auto-resolve for filer |
| **Automated Assessment** | System matches payment to delivery records, evaluates evidence, decides or escalates | Immediate | — |
| **Human Arbitration** | Packaged evidence + automated assessment sent to arbitrator | 48h → fund admin, 7d → auto-refund | Auto-refund to filer |
| **Resolution Enforcement** | Funds move atomically. Dispute record immutable. No re-opening. No appeals. | — | — |

**6 reason categories:** `service_not_delivered` · `quality_below_standard` · `unauthorized_transaction` · `amount_incorrect` · `duplicate_charge` · `other`

At every timeout, the system takes the conservative action — return money to the person who paid. That is the payments industry standard.

The Transaction Authorizer learns from disputes. Agents with >5% dispute rate get automatically tightened spending policies — lower per-transaction limits, frequently-disputed counterparties added to the blocked list, human escalation thresholds reduced. Anonymized dispute patterns feed the Sovereign Intelligence Layer to improve automated assessment confidence over time.

Full specification: [docs/dispute-resolution-protocol.md](docs/dispute-resolution-protocol.md)

---

## Exception Handling & Advanced Settlement

Production payment infrastructure requires more than authorization and settlement. These are the capabilities that separate a prototype from a system that can operate at scale:

| Capability | What It Solves |
|-----------|---------------|
| **Chargebacks** | 6 reason codes, evidence windows, automated evaluation, full or partial reversal |
| **Refunds** | Full, partial, different-wallet routing, tiered approval workflows |
| **Partial Capture** | Authorize $1,000, deliver 75%, capture $750, release $250 back to available balance |
| **Split Settlement** | One authorization distributed to multiple counterparty wallets, settled atomically |
| **Installment Plans** | Authorize once, settle in N tranches on a schedule with automatic execution |
| **Batch Settlement** | Aggregate micro-transactions into single settlement events — 50 small data purchases become one settlement |
| **Fee Engine** | 4 types (platform, processing, escrow, cross-org), configurable per org, deducted atomically |
| **Multi-Currency FX** | Rate locking during escrow so counterparty receives the agreed amount regardless of rate movement |
| **Dead Letter Queue** | Failed transactions with aging alerts (3d warning, 14d auto-abandon), SLA tracking, manual resolution |
| **Idempotency** | Client-supplied keys prevent duplicate charges on network retries or webhook re-submissions |
| **Admin Holds** | Emergency payment freeze by agent, org, or fund — existing escrows continue to resolution |
| **Credit/Debit Memos** | Post-settlement adjustments without full reversal — service credits, billing corrections, volume discounts |

**6 chargeback reason codes:** `service_not_delivered` · `service_not_as_described` · `duplicate_transaction` · `unauthorized_transaction` · `amount_error` · `fraud`

Full specifications: [Chargebacks & Refunds](docs/chargeback-refund-protocol.md) · [Settlement Operations](docs/settlement-operations.md)

---

## Reconciliation

Automated daily run at 3:00 AM UTC matching every settled payment to its service delivery record. On-demand trigger available via API.

| Detection Category | What It Finds | Severity |
|-------------------|---------------|----------|
| **Phantom payment** | Money moved, no matching service delivery record | Critical |
| **Unpaid service** | Service completed, no corresponding payment | High |
| **Amount mismatch** | Payment deviates >10% from expected cost | Medium |
| **Counterparty concentration** | >40% of volume to single counterparty | Medium |
| **Velocity anomaly** | >2x standard deviation from 30-day moving average | High |
| **Category drift** | New transaction categories without policy updates | Low |
| **Cross-org pattern** | Patterns suggesting coordinated policy circumvention | Critical |
| **Dispute rate** | Agent exceeds 5% dispute rate on transactions in period | High |

Full specification: [docs/reconciliation-framework.md](docs/reconciliation-framework.md)

---

## Spending Policies

Human judgment encoded into machine-enforceable rules. Policies cascade: fund default → org default → agent-specific. The most specific policy wins.

| Parameter | What It Controls |
|-----------|-----------------|
| `max_per_transaction` | Hard ceiling on any single transaction — exceeding this is an immediate denial |
| `max_daily` | Rolling 24-hour budget cap with atomic enforcement — no race conditions on concurrent requests |
| `max_monthly` | Rolling 30-day budget cap, same atomic enforcement |
| `approved_counterparties` | Whitelist — empty means unrestricted, non-empty means ONLY these counterparties |
| `blocked_counterparties` | Blacklist — checked BEFORE approved list, takes absolute precedence |
| `allowed_categories` | Transaction type restrictions (service_fee, data_purchase, resource_allocation, subscription, escrow) |
| `require_human_above` | Amount threshold for automatic escalation to human operator via Property Dispatcher |
| `compliance_precheck` | Enable pre-transaction regulatory scanning across configured jurisdictions |

Policy snapshots are frozen into every authorization record at decision time. If the policy is changed later, the audit trail still shows exactly what rules were in effect when the decision was made.

Full specification: [docs/spending-policy-schema.md](docs/spending-policy-schema.md)

---

## Compliance

Pre-transaction regulatory scanning embedded in the authorization pipeline at step 9. Violations blocked before money moves.

| Region | Regulatory Frameworks |
|--------|----------------------|
| **United States** | Federal regulations, state-level requirements |
| **European Union** | GDPR, PSD2, MiCA, DORA |
| **UAE** | CBUAE, DFSA, ADGM |
| **Latin America** | LGPD, BCB, CNBV |

Compliance exports with per-jurisdiction formatting, SHA-256 hash verification, and chain of custody tracking for audit integrity. Statement generation per agent, per org, or per fund — daily, weekly, or monthly — in JSON or PDF with configurable webhook delivery.

Full specifications: [docs/compliance-framework.md](docs/compliance-framework.md) · [docs/reporting-compliance-exports.md](docs/reporting-compliance-exports.md)

---

## Pulse API Routes

50 routes across 10 operational domains. SHA-256 hashed API key authentication with IP whitelisting and per-key rate limiting.

### Payment Operations (4 routes)

| Method | Route | Permission |
|--------|-------|-----------|
| `POST` | `/pulse-api/payments/request` | `payments:request` |
| `GET` | `/pulse-api/payments` | `payments:read` |
| `GET` | `/pulse-api/payments/:id` | `payments:read` |
| `GET` | `/pulse-api/payments/:id/events` | `payments:read` |

### Wallet Operations (4 routes)

| Method | Route | Permission |
|--------|-------|-----------|
| `GET` | `/pulse-api/wallets` | `wallets:read` |
| `GET` | `/pulse-api/wallets/:agent_id` | `wallets:read` |
| `POST` | `/pulse-api/wallets/:agent_id/fund` | `wallets:write` |
| `POST` | `/pulse-api/wallets/:agent_id/withdraw` | `wallets:write` |

### Policy Operations (4 routes)

| Method | Route | Permission |
|--------|-------|-----------|
| `GET` | `/pulse-api/policies` | `policies:read` |
| `POST` | `/pulse-api/policies` | `policies:write` |
| `PATCH` | `/pulse-api/policies/:id` | `policies:write` |
| `DELETE` | `/pulse-api/policies/:id` | `policies:write` |

### Reconciliation (2 routes)

| Method | Route | Permission |
|--------|-------|-----------|
| `GET` | `/pulse-api/reconciliation` | `reconciliation:read` |
| `POST` | `/pulse-api/reconciliation/trigger` | `reconciliation:trigger` |

### Dispute Operations (5 routes)

| Method | Route | Permission |
|--------|-------|-----------|
| `POST` | `/pulse-api/payments/:id/dispute` | `disputes:write` |
| `POST` | `/pulse-api/payments/:id/dispute/respond` | `disputes:write` |
| `GET` | `/pulse-api/payments/:id/dispute` | `disputes:read` |
| `POST` | `/pulse-api/payments/:id/dispute/arbitrate` | `disputes:admin` |
| `GET` | `/pulse-api/disputes` | `disputes:read` |

### Chargeback & Refund Operations (4 routes)

| Method | Route | Permission |
|--------|-------|-----------|
| `POST` | `/pulse-api/payments/:id/chargeback` | `exceptions:write` |
| `POST` | `/pulse-api/payments/:id/chargeback/respond` | `exceptions:write` |
| `POST` | `/pulse-api/payments/:id/refund` | `exceptions:write` |
| `POST` | `/pulse-api/memos` | `exceptions:write` |

### Settlement Operations (6 routes)

| Method | Route | Permission |
|--------|-------|-----------|
| `POST` | `/pulse-api/payments/:id/capture` | `settlements:write` |
| `POST` | `/pulse-api/settlements/batch` | `settlements:write` |
| `GET` | `/pulse-api/payments/dead-letter` | `exceptions:read` |
| `POST` | `/pulse-api/payments/dead-letter/:id/resolve` | `exceptions:write` |
| `POST` | `/pulse-api/holds` | `exceptions:admin` |
| `DELETE` | `/pulse-api/holds/:id` | `exceptions:admin` |

### Reporting & Compliance (4 routes)

| Method | Route | Permission |
|--------|-------|-----------|
| `GET` | `/pulse-api/statements` | `compliance:read` |
| `POST` | `/pulse-api/compliance/export` | `compliance:read` |
| `GET` | `/pulse-api/compliance/exports` | `compliance:read` |
| `GET` | `/pulse-api/analytics` | `compliance:read` |

### Fee Management (2 routes)

| Method | Route | Permission |
|--------|-------|-----------|
| `GET` | `/pulse-api/fee-policies` | `policies:read` |
| `POST` | `/pulse-api/fee-policies` | `policies:write` |

Plus **15 platform operations routes** (data ingestion, agent management, reporting, webhook CRUD, health) documented in the [API Reference](docs/api-reference.md).

**Route total: 4 + 4 + 4 + 2 + 5 + 4 + 6 + 4 + 2 + 15 = 50**

Full reference with request/response schemas: [docs/api-reference.md](docs/api-reference.md) · [spec/openapi.yaml](spec/openapi.yaml)

---

## Webhook Events

HMAC-SHA256 signed payloads delivered to registered endpoints with exponential backoff retry. Auto-disable after 10 consecutive failures with alert to org admin. Re-enable resets the failure counter.

| Event | Fires When |
|-------|-----------|
| `payment.authorized` | Transaction passes all authorization steps |
| `payment.denied` | Transaction fails any authorization check |
| `payment.settled` | Instant settlement completes or escrow releases |
| `payment.failed` | Settlement fails after all retry attempts |
| `payment.escrow_held` | Funds locked in escrow pending verification |
| `payment.escrow_released` | Escrow verification passes, funds transferred |
| `payment.escrow_expired` | Escrow timeout, funds auto-refunded |
| `payment.disputed` | Dispute raised on transaction |
| `dispute.filed` | New dispute filed by either party |
| `dispute.response_received` | Counterparty submitted response with evidence |
| `dispute.assessed` | Automated assessment completed |
| `dispute.escalated` | Dispute escalated to human arbitration |
| `dispute.resolved` | Final resolution (refund or release) executed |
| `dispute.timeout` | Phase deadline passed, automatic action taken |
| `chargeback.initiated` | Chargeback request submitted |
| `chargeback.resolved` | Chargeback resolved (reversal, partial, or denied) |
| `payment.refunded` | Refund processed (full or partial) |
| `payment.memo_issued` | Credit or debit memo created |
| `hold.placed` | Admin payment hold activated |
| `hold.released` | Admin payment hold removed |
| `settlement.batch_completed` | Batch settlement completed |
| `payment.dead_letter` | Transaction entered dead letter queue |

**Event total: 22**

Full specification: [docs/webhook-security.md](docs/webhook-security.md) · [spec/events.md](spec/events.md)

---

## Validation

284 tests. 8 real bugs found during load testing and fixed before release.

| Bug ID | What Broke | Root Cause | Fix |
|--------|-----------|------------|-----|
| ESC-RACE-001 | Concurrent dispute + expiry on same escrow | No row-level lock during state transition | SELECT FOR UPDATE on escrow row |
| ESC-RACE-002 | Release + dispute arriving in same event loop tick | State already moved, second transition finds wrong state | Guard clause checks current state, returns 409 Conflict |
| AUTH-WINDOW-001 | Daily spend off by one second at midnight UTC | `>=` boundary condition on 24-hour window | Microsecond precision with `>` operator |
| AUTH-CONCURRENT-001 | Two requests 10ms apart both overspend daily limit | Both read spend as $900 (limit $1,000), both authorize $200 | Advisory lock on agent_id + org_id serializes same-agent auth |
| WEBHOOK-RETRY-001 | Re-enabled endpoint immediately re-disabled | Failure counter not reset on re-enable | Reset consecutive_failures to 0 on re-enable |
| WALLET-PRECISION-001 | $0.01 drift over 1,000+ transactions | Floating point arithmetic on balances | All operations use numeric(12,2) with explicit ROUND |
| REC-TIMEZONE-001 | Reconciliation missing transactions across business days | Window using server timezone instead of org timezone | Window calculated from org's configured timezone |
| RLS-RECURSION-001 | 13 RLS policies across 7 tables causing infinite recursion | Policies referenced a view that itself had RLS | SECURITY DEFINER functions bypass RLS cleanly |

Full report: [docs/v1.6.5-validation-report.md](docs/v1.6.5-validation-report.md)

---

## Platform Numbers

| Metric | Count |
|--------|-------|
| Production Agents | 49 |
| Service Endpoints | 74 |
| Database Tables | 98 (all with row-level security) |
| Inter-Agent Routes | 76 |
| Pulse API Routes | 50 |
| Webhook Event Types | 22 |
| API Permissions | 29 |
| Scheduled Jobs | 8 |
| Reconciliation Detection Categories | 8 |
| Authorization Denial Reason Codes | 12 |
| Chargeback Reason Codes | 6 |
| Dispute Reason Categories | 6 |
| Dispute Resolution Phases | 5 |
| Escrow States | 5 |
| Spending Policy Parameters | 8 |
| Refund Modes | 3 (full, partial, different-wallet) |
| Fee Types | 4 (platform, processing, escrow, cross-org) |
| Settlement Modes | 3 (instant atomic, conditional escrow, external) |
| Compliance Jurisdictions | 4 regions, 12+ regulatory frameworks |
| Spec Version | 1.7.0 |

---

## SDKs

Internal SDKs provided as architectural reference. These demonstrate the complete developer surface for Pulse API integration.

### TypeScript

```typescript
import { PulsePayments } from '@tfsfventures/a2a-payments';

const pulse = new PulsePayments({ apiKey: process.env.PULSE_API_KEY });

const result = await pulse.requestPayment({
  requestingAgentId: 'agent-research-01',
  counterpartyAgentId: 'agent-content-03',
  amount: 150,
  currency: 'USD',
  txType: 'service_fee',
  description: 'Research batch 47'
});

console.log(result.decision);      // 'authorized'
console.log(result.transactionId); // 'txn_...'
```

### Python

```python
from a2a_payments import PulsePayments

pulse = PulsePayments(api_key="your-api-key")

result = pulse.request_payment(
    requesting_agent_id="agent-research-01",
    counterparty_agent_id="agent-content-03",
    amount=150,
    currency="USD",
    tx_type="service_fee",
    description="Research batch 47"
)

print(result.decision)        # "authorized"
print(result.transaction_id)  # "txn_..."
```

Full documentation: [TypeScript SDK](sdk/typescript/README.md) · [Python SDK](sdk/python/README.md)

---

## Repository Structure

```
a2a-payment-protocol/
├── README.md
├── LICENSE                                    ← Apache 2.0
├── SECURITY.md                                ← Vulnerability reporting
├── CONTRIBUTING.md                            ← Protocol contributions
├── index.html                                 ← White paper (a2a.tfsfventures.com)
│
├── spec/
│   ├── openapi.yaml                           ← OpenAPI 3.1 — all 50 routes
│   └── events.md                              ← 22 webhook + inter-agent event schemas
│
├── docs/
│   ├── quickstart.md                          ← 5-minute integration reference
│   ├── api-reference.md                       ← 50 routes, full schemas, curl examples
│   ├── architecture-overview.md               ← Three-layer architecture, 76 inter-agent routes
│   ├── authorization-protocol.md              ← 10-step pipeline, concurrent auth, design decisions
│   ├── settlement-protocol.md                 ← 3 settlement modes, "Why Not Blockchain"
│   ├── settlement-operations.md               ← Partial/batch/installment, fees, FX, DLQ, holds
│   ├── escrow-lifecycle.md                    ← 5 states, 6 transitions, edge cases
│   ├── escrow-race-conditions.md              ← 7 race conditions, 50-actor load test results
│   ├── dispute-resolution-protocol.md         ← 5-phase lifecycle, assessment, arbitration
│   ├── chargeback-refund-protocol.md          ← 6 reason codes, evidence windows, refund engine
│   ├── reconciliation-framework.md            ← 8 detection categories, AI anomaly detection
│   ├── spending-policy-schema.md              ← 8 parameters, cascade, policy snapshots
│   ├── wallet-system.md                       ← Available/held balances, atomic operations
│   ├── webhook-security.md                    ← HMAC-SHA256, retry logic, auto-disable
│   ├── compliance-framework.md                ← US/EU/UAE/LATAM regulatory scanning
│   ├── multi-tenancy-payments.md              ← Fund → portco hierarchy, policy cascade
│   ├── reporting-compliance-exports.md        ← Statements, audit exports, analytics
│   ├── changelog.md                           ← Full version history with bug fixes
│   └── v1.6.5-validation-report.md            ← 284 tests, 8 bugs found and fixed
│
├── sdk/
│   ├── typescript/                            ← TypeScript SDK (architectural reference)
│   └── python/                                ← Python SDK (architectural reference)
│
└── diagrams/
    ├── payment-flow.svg                       ← Agent → Authorizer → Executor → Auditor
    ├── authorization-pipeline.svg             ← 10-step flow with decision points
    ├── escrow-state-machine.svg               ← 5 states, 6 transitions
    └── architecture-layers.svg                ← Gateway → Payment Layer → Core Platform
```

---

## Documentation Index

| Document | Description |
|----------|-------------|
| [Quickstart](docs/quickstart.md) | 5-minute integration reference |
| [Architecture Overview](docs/architecture-overview.md) | Three-layer model, 76 inter-agent routes, org hierarchy |
| [Authorization Protocol](docs/authorization-protocol.md) | 10-step pipeline, 12 denial codes, concurrent auth, design decisions |
| [Settlement Protocol](docs/settlement-protocol.md) | 3 modes: instant atomic, conditional escrow, external |
| [Settlement Operations](docs/settlement-operations.md) | Partial capture, split/batch/installment, fee engine, FX, DLQ, holds |
| [Escrow Lifecycle](docs/escrow-lifecycle.md) | 5 states, 6 transitions, verification, expiry, disputes |
| [Escrow Race Conditions](docs/escrow-race-conditions.md) | 7 race conditions found in load testing, prevention mechanisms |
| [Dispute Resolution](docs/dispute-resolution-protocol.md) | 5-phase lifecycle, automated assessment, human arbitration |
| [Chargebacks & Refunds](docs/chargeback-refund-protocol.md) | 6 chargeback reason codes, refund engine, credit/debit memos |
| [Reconciliation Framework](docs/reconciliation-framework.md) | 8 detection categories, severity rules, AI anomaly detection |
| [Spending Policy Schema](docs/spending-policy-schema.md) | 8 parameters, fund → org → agent cascade, snapshot mechanism |
| [Wallet System](docs/wallet-system.md) | Available/held balances, atomic operations, balance invariant |
| [Webhook Security](docs/webhook-security.md) | HMAC-SHA256 signing, 22 event types, retry, auto-disable |
| [Compliance Framework](docs/compliance-framework.md) | Pre-transaction scanning, 4 jurisdictions, 12+ regulatory frameworks |
| [Multi-Tenancy Payments](docs/multi-tenancy-payments.md) | Fund → portco hierarchy, policy cascade, cross-org transactions |
| [Reporting & Exports](docs/reporting-compliance-exports.md) | Statements, jurisdiction-specific audit exports, analytics |
| [API Reference](docs/api-reference.md) | All 50 routes, full request/response schemas, curl examples |
| [Validation Report](docs/v1.6.5-validation-report.md) | 284 tests, 8 bugs documented with severity, root cause, and fix |
| [Changelog](docs/changelog.md) | Version history with Added and Fixed sections |
| [Payment Flow Diagram](diagrams/payment-flow.svg) | Agent → Authorizer → Executor → Auditor |
| [Authorization Pipeline Diagram](diagrams/authorization-pipeline.svg) | 10-step flow with decision points |
| [Escrow State Machine Diagram](diagrams/escrow-state-machine.svg) | 5 states, 6 transitions |
| [Architecture Layers Diagram](diagrams/architecture-layers.svg) | Gateway → Payment Layer → Core Platform |

---

## References

- Zhang, Y., Xiang, Y., Lei, Y., Wang, Q., et al. (2026). *SoK: Blockchain Agent-to-Agent Payments.* arXiv:2604.03733. [Paper](https://arxiv.org/abs/2604.03733)

---

## White Paper

**[a2a.tfsfventures.com →](https://a2a.tfsfventures.com)**

---

## Security

Found a vulnerability? See [SECURITY.md](SECURITY.md) for responsible disclosure instructions.

---

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.

---

## Author

**Steven Foster** — Founder & CEO, TFSF Ventures FZ-LLC

TFSF Ventures FZ-LLC · RAKEZ License 47013955 · Ras Al Khaimah, UAE

**[tfsfventures.com](https://tfsfventures.com)** · **[support@tfsfventures.com](mailto:support@tfsfventures.com)**

---

<p align="center">
  <sub>© 2026 TFSF Ventures FZ-LLC. All rights reserved.</sub>
</p>

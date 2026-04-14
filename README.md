<p align="center">
  <strong>A2A PAYMENT PROTOCOL</strong>
</p>

<h1 align="center">Agent-to-Agent Payment Infrastructure</h1>

<p align="center">
  Production-grade specification for secure, verifiable, and compliant payment infrastructure between autonomous AI agents. Architecture is public. Implementation is proprietary. Every endpoint routes through the Pulse API.
</p>

<p align="center">
  <code>v1.7.0</code> · <code>49 Production Agents</code> · <code>50 API Routes</code> · <code>22 Webhook Events</code> · <code>8 Reconciliation Categories</code>
</p>

<p align="center">
  <a href="docs/quickstart.md">Quickstart</a> · <a href="spec/openapi.yaml">OpenAPI Spec</a> · <a href="docs/v1.6.5-validation-report.md">Validation Report</a> · <a href="docs/architecture-overview.md">Architecture</a> · <a href="docs/changelog.md">Changelog</a>
</p>

<p align="center">
  <a href="https://a2a.tfsfventures.com">Read the White Paper →</a>
</p>

---

## Overview

This repository is the complete technical specification for production-grade agent-to-agent payment infrastructure. It defines how autonomous AI agents authorize, settle, dispute, reverse, and reconcile payments between each other with full compliance enforcement, conditional escrow, automated dispute resolution, and daily anomaly detection.

A [peer-reviewed SoK paper](https://arxiv.org/abs/2604.03733) published April 2026 confirmed that agent-to-agent payments represent an unsolved infrastructure gap across a four-stage lifecycle: discovery, authorization, execution, and accounting. This protocol addresses all four stages in a single system.

**This repository contains the protocol specification, architecture reference, and SDK documentation. It does not contain the implementation.** The implementation is proprietary and runs inside the Pulse AI platform. All endpoints route through the Pulse API. The specification is the contract. The infrastructure behind it is ours.

---

## The Problem

| Gap | Impact |
|-----|--------|
| No authorization model for autonomous spending | Humans must approve every agent transaction |
| No escrow primitive for multi-step agent work | Agents cannot hold funds conditionally pending delivery verification |
| No dispute resolution for agent-to-agent payments | When an agent pays for work that never arrives, there is no recourse |
| No reconciliation protocol | At 4,500+ transactions per week across a fund, manual auditing is impossible |
| No compliance-aware payment routing | Agents accidentally violate regulations across US, EU, UAE, and LATAM jurisdictions |

Traditional payment processors (Visa, Mastercard, Stripe, PayPal) are adapting consumer checkout for agent-initiated transactions. Blockchain experiments (X402, OpenClaw) address settlement but not authorization, compliance, or reconciliation. This protocol closes all four lifecycle gaps in a single system with 27 years of payments infrastructure experience behind it.

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
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐             │  │
│  │  │ TRANSACTION │ │ SETTLEMENT  │ │ RECONCIL-   │             │  │
│  │  │ AUTHORIZER  │→│ EXECUTOR    │→│ IATION      │             │  │
│  │  │    #43      │ │    #44      │ │ AUDITOR #45 │             │  │
│  │  │ 10-step     │ │ 3 modes     │ │ 8 detection │             │  │
│  │  │ pipeline    │ │ + webhooks  │ │ categories  │             │  │
│  │  └─────────────┘ └─────────────┘ └─────────────┘             │  │
│  │                                                                │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐             │  │
│  │  │ DISPUTE     │ │ EXCEPTION   │ │ SETTLEMENT  │             │  │
│  │  │ RESOLUTION  │ │ HANDLER     │ │ OPERATIONS  │             │  │
│  │  │    #46      │ │    #47      │ │    #48      │             │  │
│  │  │ 5-phase     │ │ Chargebacks │ │ Partial     │             │  │
│  │  │ lifecycle   │ │ Refunds     │ │ Split/Batch │             │  │
│  │  │ Arbitration │ │ Holds/DLQ   │ │ Fees/FX     │             │  │
│  │  └─────────────┘ └─────────────┘ └─────────────┘             │  │
│  │                                                                │  │
│  │  ┌─────────────┐                                              │  │
│  │  │ COMPLIANCE  │  76 inter-agent routes · 22 webhook events   │  │
│  │  │ REPORTER    │  8 scheduled jobs · Daily reconciliation     │  │
│  │  │    #49      │                                              │  │
│  │  │ Statements  │                                              │  │
│  │  │ Exports     │                                              │  │
│  │  │ Analytics   │                                              │  │
│  │  └─────────────┘                                              │  │
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

Every payment request passes through a **10-step authorization pipeline** before any money moves.

```
payment_request
│
├─ 0. Hold check — active payment holds block immediately
├─ 1. Load spending policy (agent-specific → org default → fund default → deny)
├─ 2. Validate amount ≤ max_per_transaction
├─ 3. Validate daily_spend + amount ≤ max_daily (rolling 24h, atomic)
├─ 4. Validate monthly_spend + amount ≤ max_monthly (rolling 30d, atomic)
├─ 5. Check counterparty (blocked list → approved list)
├─ 6. Check transaction category against allowed_categories
├─ 7. Check wallet: available_balance ≥ amount
├─ 8. If amount > require_human_above → ESCALATE to human
├─ 9. If compliance_precheck enabled → scan jurisdictions (US/EU/UAE/LATAM)
└─ 10. Decision
       │
  ┌────┴────┐
  ▼         ▼
AUTHORIZE   DENY (+ reason_code + audit record + policy snapshot)
```

**11 denial reason codes:** `no_policy` · `policy_exceeded` · `budget_exceeded` · `counterparty_blocked` · `counterparty_not_approved` · `category_restricted` · `insufficient_balance` · `compliance_fail` · `human_required` · `human_denied` · `payment_hold`

Concurrent authorization uses advisory locks. Daily/monthly spend calculated as atomic SUM across authorized + executing + settled transactions. Policy snapshots frozen into the authorization record at decision time — if the policy changes later, the audit record still shows exactly what was in effect.

Full specification: [docs/authorization-protocol.md](docs/authorization-protocol.md) · [docs/spending-policy-schema.md](docs/spending-policy-schema.md)

---

## Settlement

Three settlement modes exist because three real-world scenarios demand them:

| Mode | Use Case | Mechanism |
|------|----------|-----------|
| **Instant Atomic** | Trusted agents, same org, straightforward service fees | Atomic debit/credit in single transaction. Both wallets update simultaneously. HMAC-SHA256 webhooks to both parties. |
| **Conditional Escrow** | Cross-org transactions, delivery verification required | Funds held → verification → released to counterparty. Timeout → auto-refund. Dispute → frozen for human resolution. |
| **External** | Real money settlement between organizations | Production payment rails with authorization, fraud screening, capture, clearing, settlement, reconciliation. |

### Escrow State Machine

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
     │ funds →   │  │ funds → │  │  FROZEN   │
     │ counter-  │  │ back to │  │  (human   │
     │ party     │  │ sender  │  │  resolve) │
     └───────────┘  └─────────┘  └───────────┘
```

Seven escrow race conditions documented and fixed during 50-concurrent-actor load testing. SELECT FOR UPDATE prevents concurrent state transitions. The available_balance + held_balance invariant is maintained through every state change within atomic transactions.

Full specification: [docs/settlement-protocol.md](docs/settlement-protocol.md) · [docs/escrow-lifecycle.md](docs/escrow-lifecycle.md) · [docs/escrow-race-conditions.md](docs/escrow-race-conditions.md)

---

## Dispute Resolution

Disputes are a first-class workflow with their own 5-phase lifecycle — not a status flag on an escrow.

| Phase | What Happens | Deadline | Timeout Action |
|-------|-------------|----------|----------------|
| **Filing** | Either party files with reason category and structured evidence | — | — |
| **Counterparty Response** | Counterparty submits delivery records, output hashes, timestamps | 24h (agent) / 72h (human) | Auto-resolve for filer |
| **Automated Assessment** | System matches payment to delivery records, evaluates evidence, decides or escalates | Immediate | — |
| **Human Arbitration** | Packaged evidence + automated assessment sent to arbitrator | 48h → fund admin, 7d → auto-refund | Auto-refund to filer |
| **Resolution Enforcement** | Funds move atomically. Dispute record immutable. No re-opening. No appeals. | — | — |

**6 dispute reason categories:** `service_not_delivered` · `quality_below_standard` · `unauthorized_transaction` · `amount_incorrect` · `duplicate_charge` · `other`

At every timeout, the system takes the conservative action — return money to the person who paid. That is the payments industry standard.

Agents with >5% dispute rate get automatically tightened spending policies. Dispute patterns feed the Sovereign Intelligence Layer to improve automated assessment confidence over time.

Full specification: [docs/dispute-resolution-protocol.md](docs/dispute-resolution-protocol.md)

---

## Exception Handling & Advanced Settlement

The protocol handles the complete payment lifecycle beyond basic authorization and settlement:

| Capability | What It Does |
|-----------|--------------|
| **Chargebacks** | 6 reason codes, evidence windows, automated evaluation, full/partial reversal |
| **Refunds** | Full, partial, different-wallet routing, tiered approval workflows |
| **Partial Capture** | Authorize $1,000, settle $750, release $250 back to available balance |
| **Split Settlement** | One authorization distributed to multiple counterparty wallets atomically |
| **Installment Plans** | Authorize once, settle in N tranches on schedule |
| **Batch Settlement** | Aggregate micro-transactions into single settlement events |
| **Fee Engine** | 4 fee types: platform, processing, escrow, cross-org — configurable per org |
| **Multi-Currency FX** | Rate locking during escrow, cross-currency atomic settlement |
| **Dead Letter Queue** | Failed transactions with aging alerts, SLA tracking, manual resolution |
| **Idempotency** | Client-supplied keys prevent duplicate charges on retries |
| **Admin Holds** | Emergency payment freeze by agent, org, or fund level |
| **Credit/Debit Memos** | Post-settlement adjustments without full reversal |

Full specifications: [Chargebacks & Refunds](docs/chargeback-refund-protocol.md) · [Settlement Operations](docs/settlement-operations.md)

---

## Reconciliation

Automated daily run matching every settled payment to its service delivery record.

| Detection Category | What It Finds | Severity |
|-------------------|---------------|----------|
| **Phantom payment** | Money moved, no matching service delivery record | Critical |
| **Unpaid service** | Service completed, no corresponding payment | High |
| **Amount mismatch** | Payment deviates >10% from expected cost | Medium |
| **Counterparty concentration** | Unusual payment volume to single counterparty | Medium |
| **Velocity anomaly** | Spending rate exceeds historical patterns | High |
| **Category drift** | New transaction categories without policy updates | Low |
| **Cross-org pattern** | Patterns suggesting coordinated policy circumvention | Critical |
| **Dispute rate** | Agent exceeds 5% dispute rate on transactions | High |

Full specification: [docs/reconciliation-framework.md](docs/reconciliation-framework.md)

---

## Spending Policy

Human judgment encoded into machine-enforceable rules. Policies cascade from fund → org → agent.

| Parameter | What It Controls |
|-----------|-----------------|
| `max_per_transaction` | Hard ceiling on any single transaction |
| `max_daily` | Rolling 24-hour budget, atomic enforcement |
| `max_monthly` | Rolling 30-day budget, atomic enforcement |
| `approved_counterparties` | Whitelist of permitted counterparties |
| `blocked_counterparties` | Blacklist — checked first, takes absolute precedence |
| `allowed_categories` | Transaction type restrictions |
| `require_human_above` | Auto-escalation threshold |
| `compliance_precheck` | Enable pre-transaction regulatory scanning |

Policy snapshots are frozen into every authorization record. If the policy changes later, the audit trail still shows exactly what rules were in effect at decision time.

Full specification: [docs/spending-policy-schema.md](docs/spending-policy-schema.md)

---

## Compliance

Pre-transaction regulatory scanning embedded in the authorization pipeline at step 9.

| Region | Frameworks |
|--------|-----------|
| **United States** | Federal regulations, state-level requirements |
| **European Union** | GDPR, PSD2, MiCA, DORA |
| **UAE** | CBUAE, DFSA, ADGM |
| **Latin America** | LGPD, BCB, CNBV |

Compliance exports with per-jurisdiction formatting, SHA-256 hash verification, and chain of custody tracking. Statement generation per agent, per org, or per fund in JSON or PDF with configurable delivery schedules.

Full specifications: [docs/compliance-framework.md](docs/compliance-framework.md) · [docs/reporting-compliance-exports.md](docs/reporting-compliance-exports.md)

---

## Pulse API Routes

50 routes. 29 permissions. SHA-256 hashed API key authentication with IP whitelisting.

### Payment Operations

| Method | Route | Permission |
|--------|-------|-----------|
| `POST` | `/pulse-api/payments/request` | `payments:request` |
| `GET` | `/pulse-api/payments` | `payments:read` |
| `GET` | `/pulse-api/payments/:id` | `payments:read` |
| `GET` | `/pulse-api/payments/:id/events` | `payments:read` |
| `POST` | `/pulse-api/payments/:id/capture` | `settlements:write` |

### Wallet Operations

| Method | Route | Permission |
|--------|-------|-----------|
| `GET` | `/pulse-api/wallets` | `wallets:read` |
| `GET` | `/pulse-api/wallets/:agent_id` | `wallets:read` |
| `POST` | `/pulse-api/wallets/:agent_id/fund` | `wallets:write` |
| `POST` | `/pulse-api/wallets/:agent_id/withdraw` | `wallets:write` |

### Policy Operations

| Method | Route | Permission |
|--------|-------|-----------|
| `GET` | `/pulse-api/policies` | `policies:read` |
| `POST` | `/pulse-api/policies` | `policies:write` |
| `PATCH` | `/pulse-api/policies/:id` | `policies:write` |
| `DELETE` | `/pulse-api/policies/:id` | `policies:write` |

### Reconciliation

| Method | Route | Permission |
|--------|-------|-----------|
| `GET` | `/pulse-api/reconciliation` | `reconciliation:read` |
| `POST` | `/pulse-api/reconciliation/trigger` | `reconciliation:trigger` |

### Dispute Operations

| Method | Route | Permission |
|--------|-------|-----------|
| `POST` | `/pulse-api/payments/:id/dispute` | `disputes:write` |
| `POST` | `/pulse-api/payments/:id/dispute/respond` | `disputes:write` |
| `GET` | `/pulse-api/payments/:id/dispute` | `disputes:read` |
| `POST` | `/pulse-api/payments/:id/dispute/arbitrate` | `disputes:admin` |
| `GET` | `/pulse-api/disputes` | `disputes:read` |

### Chargeback & Refund Operations

| Method | Route | Permission |
|--------|-------|-----------|
| `POST` | `/pulse-api/payments/:id/chargeback` | `exceptions:write` |
| `POST` | `/pulse-api/payments/:id/chargeback/respond` | `exceptions:write` |
| `POST` | `/pulse-api/payments/:id/refund` | `exceptions:write` |
| `POST` | `/pulse-api/memos` | `exceptions:write` |

### Settlement Operations

| Method | Route | Permission |
|--------|-------|-----------|
| `POST` | `/pulse-api/settlements/batch` | `settlements:write` |
| `GET` | `/pulse-api/payments/dead-letter` | `exceptions:read` |
| `POST` | `/pulse-api/payments/dead-letter/:id/resolve` | `exceptions:write` |
| `POST` | `/pulse-api/holds` | `exceptions:admin` |
| `DELETE` | `/pulse-api/holds/:id` | `exceptions:admin` |

### Reporting & Analytics

| Method | Route | Permission |
|--------|-------|-----------|
| `GET` | `/pulse-api/statements` | `compliance:read` |
| `POST` | `/pulse-api/compliance/export` | `compliance:write` |
| `GET` | `/pulse-api/analytics` | `compliance:read` |

### Fee Management

| Method | Route | Permission |
|--------|-------|-----------|
| `GET` | `/pulse-api/fee-policies` | `policies:read` |
| `POST` | `/pulse-api/fee-policies` | `policies:write` |

Full reference with request/response schemas: [docs/api-reference.md](docs/api-reference.md) · [spec/openapi.yaml](spec/openapi.yaml)

---

## Webhook Events

HMAC-SHA256 signed payloads with exponential backoff retry and auto-disable after 10 consecutive failures.

| Event | Fires When |
|-------|-----------|
| `payment.authorized` | Transaction passes all 10 authorization steps |
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

Full specification: [docs/webhook-security.md](docs/webhook-security.md) · [spec/events.md](spec/events.md)

---

## Validation

The protocol implementation was validated with 284 tests. During validation, 8 real bugs were found and fixed:

| Bug ID | What Happened | Fix |
|--------|--------------|-----|
| ESC-RACE-001 | Concurrent dispute + expiry on same escrow in same second | SELECT FOR UPDATE on escrow row |
| ESC-RACE-002 | Release + dispute in same event loop tick | State guard clause, 409 Conflict on moved state |
| AUTH-WINDOW-001 | Daily spend off by one second at midnight UTC | Microsecond precision on window boundary |
| AUTH-CONCURRENT-001 | Two requests 10ms apart both overspend daily limit | Advisory lock on agent_id + org_id |
| WEBHOOK-RETRY-001 | Failure counter not reset on endpoint re-enable | Reset consecutive_failures to 0 |
| WALLET-PRECISION-001 | $0.01 drift over 1,000+ transactions | numeric(12,2) with explicit ROUND, zero floating point |
| REC-TIMEZONE-001 | Reconciliation window using server TZ instead of org TZ | Window calculated from org configured timezone |
| RLS-RECURSION-001 | 13 RLS policies causing infinite recursion | SECURITY DEFINER functions bypass RLS |

Full report: [docs/v1.6.5-validation-report.md](docs/v1.6.5-validation-report.md)

---

## Platform Numbers

| Metric | Value |
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
| Chargeback Reason Codes | 6 |
| Dispute Reason Categories | 6 |
| Dispute Resolution Phases | 5 (filing → response → assessment → arbitration → enforcement) |
| Refund Modes | Full, partial, different-wallet |
| Fee Types | 4 (platform, processing, escrow, cross-org) |
| Settlement Modes | 3 (instant atomic, conditional escrow, external) |
| Compliance Jurisdictions | US, EU, UAE, LATAM (12+ regulatory frameworks) |
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
console.log(result.transactionId); // 'txn_abc123...'
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
print(result.transaction_id)  # "txn_abc123..."
```

Full SDK documentation: [TypeScript](sdk/typescript/README.md) · [Python](sdk/python/README.md)

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
│   ├── quickstart.md                          ← 5-minute integration guide
│   ├── api-reference.md                       ← 50 routes, full schemas, curl examples
│   ├── architecture-overview.md               ← Three-layer architecture, 76 inter-agent routes
│   ├── authorization-protocol.md              ← 10-step pipeline, race conditions, design decisions
│   ├── settlement-protocol.md                 ← Instant, escrow, external — "Why Not Blockchain"
│   ├── settlement-operations.md               ← Partial/batch/installment, fees, FX, DLQ, holds
│   ├── escrow-lifecycle.md                    ← 5 states, all transitions, edge cases
│   ├── escrow-race-conditions.md              ← 7 race conditions, load test results
│   ├── dispute-resolution-protocol.md         ← 5-phase lifecycle, automated assessment, arbitration
│   ├── chargeback-refund-protocol.md          ← Chargebacks, refunds, memos, evidence flows
│   ├── reconciliation-framework.md            ← 8 detection categories, AI anomaly detection
│   ├── spending-policy-schema.md              ← 8 parameters, inheritance, cascade, snapshots
│   ├── wallet-system.md                       ← Available/held balances, atomic ops
│   ├── webhook-security.md                    ← HMAC-SHA256, 22 events, retry, auto-disable
│   ├── compliance-framework.md                ← US/EU/UAE/LATAM regulatory scanning
│   ├── multi-tenancy-payments.md              ← Fund → portco hierarchy, policy cascade
│   ├── reporting-compliance-exports.md        ← Statements, audit exports, analytics
│   ├── changelog.md                           ← Version history with bug fixes
│   └── v1.6.5-validation-report.md            ← 284 tests, 8 bugs found and fixed
│
├── sdk/
│   ├── typescript/                            ← TypeScript SDK (architectural reference)
│   └── python/                                ← Python SDK (architectural reference)
│
└── diagrams/
    ├── payment-flow.svg                       ← Agent → Authorizer → Executor → Auditor
    ├── authorization-pipeline.svg             ← 10-step flow with decision diamonds
    ├── escrow-state-machine.svg               ← held → released / expired / disputed
    └── architecture-layers.svg                ← Gateway → Payment Layer → Core Platform
```

---

## Documentation Index

| Document | Description |
|----------|-------------|
| [Architecture Overview](docs/architecture-overview.md) | Three-layer model, 76 inter-agent routes, org hierarchy |
| [Authorization Protocol](docs/authorization-protocol.md) | 10-step pipeline, policy resolution, 11 reason codes, race conditions |
| [Settlement Protocol](docs/settlement-protocol.md) | Instant, escrow, external modes — "Why Not Blockchain" |
| [Settlement Operations](docs/settlement-operations.md) | Partial capture, split/batch/installment, fees, FX, DLQ, holds |
| [Escrow Lifecycle](docs/escrow-lifecycle.md) | 5 states, all transitions, verification, expiry, disputes |
| [Escrow Race Conditions](docs/escrow-race-conditions.md) | 7 race conditions, load test results, prevention mechanisms |
| [Dispute Resolution](docs/dispute-resolution-protocol.md) | 5-phase lifecycle, automated assessment, human arbitration |
| [Chargebacks & Refunds](docs/chargeback-refund-protocol.md) | Chargeback pipeline, refund engine, credit/debit memos |
| [Reconciliation Framework](docs/reconciliation-framework.md) | 8 detection categories, severity rules, AI anomaly detection |
| [Spending Policy Schema](docs/spending-policy-schema.md) | 8 parameters, inheritance, cascade, snapshot mechanism |
| [Wallet System](docs/wallet-system.md) | Available/held balances, atomic operations |
| [Webhook Security](docs/webhook-security.md) | HMAC-SHA256 signing, 22 events, retry, auto-disable |
| [Compliance Framework](docs/compliance-framework.md) | Pre-transaction scanning, 4 jurisdictions, 12+ frameworks |
| [Multi-Tenancy Payments](docs/multi-tenancy-payments.md) | Fund → portco hierarchy, policy cascade, cross-org flows |
| [Reporting & Exports](docs/reporting-compliance-exports.md) | Statements, compliance audit exports, analytics |
| [API Reference](docs/api-reference.md) | 50 routes, full schemas, curl examples |
| [Validation Report](docs/v1.6.5-validation-report.md) | 284 tests, 8 bugs documented with root cause and fix |
| [Changelog](docs/changelog.md) | Full version history with bug fixes |

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

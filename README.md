<div align="center">

# A2A Payment Protocol

### Autonomous Agent-to-Agent Financial Operations

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Spec](https://img.shields.io/badge/Spec-v1.7.0-green.svg)](spec/)
[![Status](https://img.shields.io/badge/Status-Stable-green.svg)]()

</div>

---

## Overview

> **New here?** [Get started in 5 minutes →](docs/quickstart.md)

The **A2A Payment Protocol** defines a standardised framework for autonomous AI agents to authorise, execute, and reconcile financial transactions without human intervention at the point of sale. It extends the [Google A2A (Agent-to-Agent) protocol](https://github.com/google/A2A) with a payments-specific layer that handles authorisation, escrow, settlement, and compliance across multi-agent workflows.

This repository contains the **protocol specification**, **architecture diagrams**, and **reference documentation**. It does **not** contain runnable code — the reference implementation lives in the [Pulse AI platform](https://tfsfventures.com).

---

## Problem

Modern AI agent systems can collaborate on complex tasks, but the moment money changes hands the workflow breaks:

| Gap | Impact |
|-----|--------|
| No standard payment message format between agents | Every integration is bespoke |
| No delegated spending authority model | Humans must approve every transaction |
| No escrow primitive for multi-step work | Agents cannot hold funds conditionally |
| No reconciliation protocol | Post-hoc auditing is manual |
| No compliance-aware routing | Agents accidentally violate sanctions / limits |

The A2A Payment Protocol fills each of these gaps with a minimal, composable set of primitives.

---

## Repository Structure

```
a2a-payment-protocol/
├── README.md                                  ← You are here
├── LICENSE                                    ← Apache 2.0
├── SECURITY.md                                ← Vulnerability reporting
├── CONTRIBUTING.md                            ← How to contribute
├── index.html                                 ← White paper redirect
│
├── spec/
│   ├── openapi.yaml                           ← OpenAPI 3.1 — all 50 routes
│   └── events.md                              ← 22 webhook + inter-agent event schemas
│
├── docs/
│   ├── quickstart.md                          ← Internal integration reference (5-min guide)
│   ├── api-reference.md                       ← Full API reference, all routes, curl examples
│   ├── architecture-overview.md               ← Three-layer architecture, 49 inter-agent routes
│   ├── authorization-protocol.md              ← 10-step pipeline, race conditions, policy resolution
│   ├── settlement-protocol.md                 ← Instant, escrow, external modes, "Why Not Blockchain"
│   ├── settlement-operations.md               ← Partial/batch/installment, fees, FX, DLQ, holds
│   ├── escrow-lifecycle.md                    ← 5 states, all transitions, edge cases
│   ├── escrow-race-conditions.md              ← 7 race conditions, load test results, SELECT FOR UPDATE
│   ├── dispute-resolution-protocol.md         ← 5-phase lifecycle, automated assessment, arbitration
│   ├── chargeback-refund-protocol.md          ← Chargebacks, refunds, memos, evidence flows
│   ├── reconciliation-framework.md            ← 8 detection categories, severity rules, AI anomaly detection
│   ├── spending-policy-schema.md              ← 8 parameters, inheritance, cascade, snapshots
│   ├── wallet-system.md                       ← Available/held balances, atomic ops, multi-currency
│   ├── webhook-security.md                    ← HMAC-SHA256, 22 events, retry, auto-disable
│   ├── compliance-framework.md                ← Pre-tx scanning, US/EU/UAE/LATAM jurisdictions
│   ├── multi-tenancy-payments.md              ← Fund → portco hierarchy, policy cascade, cross-org
│   ├── reporting-compliance-exports.md        ← Statements, compliance exports, analytics
│   ├── changelog.md                           ← Version history with bug fixes
│   └── v1.6.5-validation-report.md            ← 284 tests, 8 bugs found and fixed
│
├── sdk/
│   ├── typescript/                            ← TypeScript SDK (internal reference)
│   │   ├── package.json
│   │   ├── tsconfig.json
│   │   ├── README.md
│   │   └── src/
│   │       ├── index.ts
│   │       ├── client.ts                      ← Full typed client, 16 methods
│   │       ├── types.ts                       ← All request/response types + enums
│   │       ├── errors.ts                      ← Typed error hierarchy
│   │       └── webhook.ts                     ← HMAC verification
│   └── python/                                ← Python SDK (internal reference)
│       ├── pyproject.toml
│       ├── README.md
│       └── src/a2a_payments/
│           ├── __init__.py
│           ├── client.py                      ← Full httpx client, 16 methods
│           ├── types.py                       ← Dataclass models + enums
│           ├── exceptions.py                  ← Typed error hierarchy
│           └── webhook.py                     ← HMAC verification
│
└── diagrams/
    ├── payment-flow.svg                       ← Agent → Authorizer → Executor → Auditor
    ├── authorization-pipeline.svg             ← 10-step flow with decision diamonds
    ├── escrow-state-machine.svg               ← held → released / expired / disputed
    └── architecture-layers.svg                ← Gateway → Payment Layer → Core Platform
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    PLATFORM GATEWAY                          │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐ │
│  │ Auth    │  │ Rate     │  │ Compliance│  │ Webhook     │ │
│  │ Service │  │ Limiter  │  │ Engine   │  │ Dispatcher  │ │
│  └────┬────┘  └────┬─────┘  └────┬─────┘  └──────┬──────┘ │
│       │            │             │                │         │
│  ┌────▼────────────▼─────────────▼────────────────▼──────┐ │
│  │              MESSAGE ROUTER (A2A Protocol)             │ │
│  └────┬──────────┬──────────┬──────────┬────────────┬────┘ │
│       │          │          │          │            │       │
│  ┌────▼───┐ ┌───▼────┐ ┌──▼───┐ ┌───▼─────┐ ┌───▼────┐  │
│  │Payment │ │Escrow  │ │Ledger│ │Reconcil-│ │Spending│  │
│  │Agent   │ │Agent   │ │Agent │ │iation   │ │Policy  │  │
│  │(#43)   │ │(#44)   │ │(#45) │ │Agent    │ │Agent   │  │
│  └────────┘ └────────┘ └──────┘ └─────────┘ └────────┘  │
│                                                           │
│  ┌───────────────────────────────────────────────────────┐ │
│  │              SETTLEMENT LAYER                         │ │
│  │  Stripe Connect  │  Wise Business  │  Crypto Rails   │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## Authorization Pipeline

The protocol implements a **four-stage authorization pipeline** that every payment request must traverse:

```
Request → [1. Identity] → [2. Policy] → [3. Compliance] → [4. Settlement] → Complete
              │               │              │                │
              ▼               ▼              ▼                ▼
          Verify agent    Check spending  Screen against   Route to
          credentials     limits & rules  sanctions lists  payment rail
```

### Stage Details

| Stage | Component | Checks | Fail Action |
|-------|-----------|--------|-------------|
| 1. Identity | Auth Service | Agent API key, session token, delegation chain | Reject with `AUTH_FAILED` |
| 2. Policy | Spending Policy Agent | Per-txn limit, daily/monthly budget, merchant category | Reject with `POLICY_VIOLATION` |
| 3. Compliance | Compliance Engine | OFAC/EU sanctions, PEP screening, jurisdiction rules | Hold for manual review |
| 4. Settlement | Payment Agent | Balance check, rail availability, currency support | Queue for retry |

---

## Settlement Modes

The protocol supports three settlement modes:

### 1. Instant Settlement
Direct payment execution. Funds move immediately from payer to payee.

### 2. Escrow Settlement
Funds are locked in escrow and released upon condition fulfilment.

### 3. Deferred Settlement
Payment is recorded but settlement occurs in a batch window.

### Escrow State Machine

```
                    ┌──────────┐
         ┌─────────│  CREATED  │─────────┐
         │         └──────────┘         │
         ▼                              ▼
   ┌──────────┐                  ┌──────────┐
   │  FUNDED  │                  │ CANCELLED │
   └─────┬────┘                  └──────────┘
         │
    ┌────▼────┐
    │ LOCKED  │──────────┐
    └────┬────┘          │
         │               ▼
    ┌────▼─────┐   ┌──────────┐
    │ RELEASED │   │ DISPUTED │
    └──────────┘   └─────┬────┘
                         │
                    ┌────▼─────┐
                    │ RESOLVED │
                    └──────────┘
```

---

## Reconciliation

Every transaction produces a **reconciliation record** that can be verified by any party:

| Field | Type | Description |
|-------|------|-------------|
| `txn_id` | `string` | Unique transaction identifier (UUIDv7) |
| `protocol_version` | `string` | Protocol version used (`1.0.0`) |
| `payer_agent_id` | `string` | Authenticated agent ID of payer |
| `payee_agent_id` | `string` | Authenticated agent ID of payee |
| `amount` | `object` | `{ value: string, currency: string }` |
| `settlement_mode` | `enum` | `instant \| escrow \| deferred` |
| `status` | `enum` | `pending \| completed \| failed \| disputed` |
| `escrow_id` | `string?` | Escrow reference (if applicable) |
| `compliance_result` | `object` | Screening outcome + rule version |
| `timestamps` | `object` | `{ created, authorized, settled, reconciled }` |
| `signatures` | `array` | Ed25519 signatures from both agents |

---

## Dispute Resolution

Disputes are a first-class workflow with their own 5-phase lifecycle, not a status flag on an escrow.

| Phase | What Happens | Deadline | Timeout Action |
|-------|-------------|----------|----------------|
| **Filing** | Either party files with reason category and structured evidence | — | — |
| **Counterparty Response** | Counterparty submits evidence (delivery records, output hashes, timestamps) | 24h (agent) / 72h (human) | Auto-resolve for filer |
| **Automated Assessment** | System matches payment to delivery records, evaluates evidence, decides or escalates | Immediate | — |
| **Human Arbitration** | Evidence + assessment sent to arbitrator via Property Dispatcher | 48h then fund admin, 7d then auto-refund | Auto-refund to filer |
| **Resolution Enforcement** | Funds move atomically. Dispute record immutable. No re-opening. | — | — |

6 dispute reason categories: `service_not_delivered` · `quality_below_standard` · `unauthorized_transaction` · `amount_incorrect` · `duplicate_charge` · `other`

At every timeout, the system takes the conservative action — return money to the person who paid.

The Transaction Authorizer learns from disputes — agents with >5% dispute rate get automatically tightened spending policies.

Full specification: [docs/dispute-resolution-protocol.md](docs/dispute-resolution-protocol.md)

---

## Exception Handling & Advanced Settlement

The protocol handles the complete payment lifecycle beyond basic authorization and settlement:

- **Chargebacks** — 6 reason codes, evidence windows, automated evaluation, full/partial reversal
- **Refunds** — Full, partial, different-wallet routing, tiered approval workflows
- **Partial Settlement** — Partial capture, split settlement across multiple counterparties, installment plans
- **Fee Engine** — 4 fee types (platform, processing, escrow, cross-org) with configurable rates
- **Multi-Currency FX** — Rate locking during escrow, cross-currency atomic settlement
- **Batch Settlement** — Aggregate micro-transactions into single settlement events
- **Dead Letter Queue** — Failed transactions with aging alerts and SLA tracking
- **Idempotency** — Client-supplied keys prevent duplicate charges on retries
- **Admin Holds** — Emergency payment freeze by agent, org, or fund
- **Credit/Debit Memos** — Post-settlement adjustments without full refund
- **Compliance Exports** — Per-jurisdiction audit formatting with SHA-256 hash verification

Full specifications: [Chargebacks & Refunds](docs/chargeback-refund-protocol.md) · [Settlement Operations](docs/settlement-operations.md) · [Reporting & Exports](docs/reporting-compliance-exports.md)

---

## Spending Policy Parameters

Policies are defined per-agent and can be delegated through a chain:

```json
{
  "policy_id": "pol_abc123",
  "agent_id": "agent_43",
  "delegated_by": "agent_orchestrator",
  "limits": {
    "per_transaction": { "value": "500.00", "currency": "USD" },
    "daily_budget": { "value": "5000.00", "currency": "USD" },
    "monthly_budget": { "value": "50000.00", "currency": "USD" }
  },
  "allowed_categories": ["cloud_services", "api_subscriptions", "contractor_payments"],
  "blocked_jurisdictions": ["KP", "IR", "SY"],
  "require_escrow_above": { "value": "1000.00", "currency": "USD" },
  "delegation_depth": 2,
  "expires_at": "2026-12-31T23:59:59Z"
}
```

---

## Pulse API Routes

The protocol exposes the following REST endpoints under the `/pulse-api/` prefix:

### Payment Operations

| Method | Route | Description |
|--------|-------|-------------|
| `POST` | `/pulse-api/payments` | Initiate a new payment |
| `GET` | `/pulse-api/payments/:id` | Get payment status |
| `POST` | `/pulse-api/payments/:id/authorize` | Authorize a pending payment |
| `POST` | `/pulse-api/payments/:id/capture` | Capture an authorized payment |
| `POST` | `/pulse-api/payments/:id/cancel` | Cancel a pending payment |
| `POST` | `/pulse-api/payments/:id/refund` | Refund a completed payment |

### Escrow Operations

| Method | Route | Description |
|--------|-------|-------------|
| `POST` | `/pulse-api/escrow` | Create an escrow |
| `GET` | `/pulse-api/escrow/:id` | Get escrow status |
| `POST` | `/pulse-api/escrow/:id/fund` | Fund an escrow |
| `POST` | `/pulse-api/escrow/:id/release` | Release escrow funds |
| `POST` | `/pulse-api/escrow/:id/dispute` | Dispute an escrow |

### Policy & Compliance

| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/pulse-api/policies/:agent_id` | Get agent spending policy |
| `PUT` | `/pulse-api/policies/:agent_id` | Update spending policy |
| `POST` | `/pulse-api/compliance/screen` | Screen a transaction |
| `GET` | `/pulse-api/compliance/rules` | Get active compliance rules |

### Reconciliation

| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/pulse-api/reconciliation/:txn_id` | Get reconciliation record |
| `POST` | `/pulse-api/reconciliation/verify` | Verify a reconciliation record |
| `GET` | `/pulse-api/reconciliation/report` | Generate reconciliation report |

### Dispute Operations

| Method | Route | Permission |
|--------|-------|-----------|
| `POST` | `/pulse-api/payments/:id/dispute` | `payments:write` |
| `POST` | `/pulse-api/payments/:id/dispute/respond` | `payments:write` |
| `GET` | `/pulse-api/payments/:id/dispute` | `payments:read` |
| `POST` | `/pulse-api/payments/:id/dispute/arbitrate` | `payments:write` |
| `GET` | `/pulse-api/disputes` | `payments:read` |

### Chargeback & Refund Operations

| Method | Route | Permission |
|--------|-------|-----------|
| `POST` | `/pulse-api/payments/:id/chargeback` | `payments:write` |
| `POST` | `/pulse-api/payments/:id/chargeback/respond` | `payments:write` |
| `POST` | `/pulse-api/payments/:id/refund` | `payments:write` |
| `POST` | `/pulse-api/memos` | `payments:write` |

### Settlement Operations

| Method | Route | Permission |
|--------|-------|-----------|
| `POST` | `/pulse-api/payments/:id/capture` | `payments:write` |
| `POST` | `/pulse-api/settlements/batch` | `payments:write` |
| `GET` | `/pulse-api/payments/dead-letter` | `payments:read` |
| `POST` | `/pulse-api/payments/dead-letter/:id/resolve` | `payments:write` |
| `POST` | `/pulse-api/holds` | `policies:write` |
| `DELETE` | `/pulse-api/holds/:id` | `policies:write` |

### Reporting & Analytics

| Method | Route | Permission |
|--------|-------|-----------|
| `GET` | `/pulse-api/statements` | `reconciliation:read` |
| `POST` | `/pulse-api/compliance/export` | `reconciliation:read` |
| `GET` | `/pulse-api/analytics` | `reconciliation:read` |

### Fee Management

| Method | Route | Permission |
|--------|-------|-----------|
| `GET` | `/pulse-api/fee-policies` | `policies:read` |
| `POST` | `/pulse-api/fee-policies` | `policies:write` |

---

## Webhook Events

The protocol emits the following webhook events:

| Event | Trigger | Payload |
|-------|---------|---------|
| `payment.created` | New payment initiated | Payment object |
| `payment.authorized` | Payment passes all four stages | Payment + auth result |
| `payment.settled` | Funds successfully transferred | Payment + settlement proof |
| `payment.failed` | Payment failed at any stage | Payment + error details |
| `payment.refunded` | Refund processed | Payment + refund details |
| `escrow.created` | New escrow created | Escrow object |
| `escrow.funded` | Escrow funded | Escrow + funding proof |
| `escrow.released` | Escrow released to payee | Escrow + release proof |
| `escrow.disputed` | Dispute raised | Escrow + dispute details |
| `compliance.hold` | Transaction held for review | Transaction + screening result |
| `policy.violation` | Spending policy violated | Transaction + policy details |
| `payment.dispute_filed` | New dispute filed | Dispute object |
| `payment.dispute_response` | Counterparty submitted evidence | Dispute + evidence details |
| `payment.dispute_assessed` | Automated assessment completed | Dispute + assessment result |
| `payment.dispute_escalated` | Escalated to human arbitration | Dispute + escalation details |
| `payment.dispute_resolved` | Final resolution executed | Dispute + resolution details |
| `payment.dispute_timeout` | Phase deadline passed | Dispute + timeout details |
| `payment.chargeback_initiated` | Chargeback request submitted | Chargeback object |
| `payment.chargeback_resolved` | Chargeback resolved | Chargeback + resolution details |
| `payment.refunded` | Refund processed | Payment + refund details |
| `payment.memo_issued` | Credit/debit memo created | Memo object |
| `payment.hold_placed` | Admin hold activated | Hold object |
| `payment.hold_released` | Admin hold removed | Hold + release details |
| `payment.batch_settled` | Batch settlement completed | Batch settlement details |
| `payment.dead_letter` | Transaction entered dead letter queue | Dead letter entry details |

---

## Inter-Agent Communication

The protocol uses the A2A message format with payment-specific extensions:

```json
{
  "a2a_version": "1.0",
  "message_type": "payment.request",
  "sender": {
    "agent_id": "agent_43",
    "agent_name": "PaymentAgent",
    "capabilities": ["payment.send", "payment.receive", "escrow.create"]
  },
  "receiver": {
    "agent_id": "agent_44",
    "agent_name": "EscrowAgent"
  },
  "payload": {
    "action": "escrow.create",
    "params": {
      "amount": { "value": "2500.00", "currency": "USD" },
      "conditions": [
        { "type": "deliverable_approved", "approver": "agent_orchestrator" },
        { "type": "time_limit", "deadline": "2026-04-21T00:00:00Z" }
      ],
      "payer": "agent_43",
      "payee": "agent_external_contractor"
    }
  },
  "metadata": {
    "correlation_id": "corr_xyz789",
    "idempotency_key": "idem_abc123",
    "timestamp": "2026-04-14T12:00:00Z"
  }
}
```

---

## Compliance Coverage

The compliance engine screens transactions against:

| Dataset | Source | Update Frequency |
|---------|--------|-----------------|
| OFAC SDN List | US Treasury | Daily |
| EU Consolidated Sanctions | EU Council | Daily |
| UN Security Council | United Nations | Weekly |
| PEP Database | Dow Jones / Refinitiv | Weekly |
| High-Risk Jurisdictions | FATF | Quarterly |

### Validation Rules

| Rule | Threshold | Action |
|------|-----------|--------|
| Single transaction limit | Configurable per agent | Reject or escalate |
| Velocity check (count) | N transactions per window | Temporary hold |
| Velocity check (amount) | Cumulative amount per window | Temporary hold |
| Jurisdiction screening | Blocked country list | Reject |
| Sanctions screening | Match score > 0.85 | Hold for review |
| PEP screening | Match score > 0.80 | Hold for review |

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
| Settlement Modes | 3 (instant, escrow, external) |
| Compliance Export Formats | US, EU, UAE, LATAM |
| Supported Currencies | 35+ |
| Protocol Version | 1.7.0 |

---

## SDKs

Install and start making agent payments in minutes.

### TypeScript

```bash
npm install @tfsfventures/a2a-payments
```

```typescript
import { PulsePayments } from '@tfsfventures/a2a-payments';

const pulse = new PulsePayments({ apiKey: process.env.PULSE_API_KEY });
const result = await pulse.requestPayment({
  requestingAgentId: 'agent-research-01',
  counterpartyAgentId: 'agent-content-03',
  amount: 150,
  currency: 'USD',
  txType: 'service_fee',
});
```

### Python

```bash
pip install a2a-payments
```

```python
from a2a_payments import PulsePayments

pulse = PulsePayments(api_key="your-api-key")
result = pulse.request_payment({
    "requesting_agent_id": "agent-research-01",
    "counterparty_agent_id": "agent-content-03",
    "amount": 150,
    "currency": "USD",
    "tx_type": "service_fee",
})
```

Full SDK documentation: [TypeScript](sdk/typescript/README.md) | [Python](sdk/python/README.md)

---

## Diagrams

| Diagram | Location | Description |
|---------|----------|-------------|
| Architecture | [`diagrams/architecture-layers.svg`](diagrams/architecture-layers.svg) | High-level system architecture |
| Auth Flow | [`diagrams/authorization-pipeline.svg`](diagrams/authorization-pipeline.svg) | Four-stage authorization pipeline |
| Escrow FSM | [`diagrams/escrow-state-machine.svg`](diagrams/escrow-state-machine.svg) | Escrow state machine |
| Settlement Flow | [`diagrams/payment-flow.svg`](diagrams/payment-flow.svg) | End-to-end settlement sequence |

---

## Documentation Index

| Document | Description |
|----------|-------------|
| [`spec/openapi.yaml`](spec/openapi.yaml) | OpenAPI 3.1 specification |
| [`spec/events.md`](spec/events.md) | Webhook and inter-agent event schemas |
| [`docs/api-reference.md`](docs/api-reference.md) | API reference with error codes |
| [`docs/webhook-security.md`](docs/webhook-security.md) | Webhook security and extensions |
| [`docs/architecture-overview.md`](docs/architecture-overview.md) | Architecture deep-dive |
| [`docs/authorization-protocol.md`](docs/authorization-protocol.md) | Spending policy model |
| [`docs/settlement-protocol.md`](docs/settlement-protocol.md) | Settlement flows |
| [`docs/reconciliation-framework.md`](docs/reconciliation-framework.md) | Reconciliation protocol |
| [`docs/compliance-framework.md`](docs/compliance-framework.md) | Compliance framework |
| [`docs/quickstart.md`](docs/quickstart.md) | Your first agent payment in 5 minutes |
| [`docs/escrow-race-conditions.md`](docs/escrow-race-conditions.md) | Deep dive: preventing money from disappearing |
| [`docs/escrow-lifecycle.md`](docs/escrow-lifecycle.md) | Escrow state machine and lifecycle |
| [`docs/spending-policy-schema.md`](docs/spending-policy-schema.md) | Spending policy parameters and inheritance |
| [`docs/wallet-system.md`](docs/wallet-system.md) | Agent wallet architecture |
| [`docs/multi-tenancy-payments.md`](docs/multi-tenancy-payments.md) | Multi-tenant payment isolation |
| [`docs/changelog.md`](docs/changelog.md) | Version history with bug fixes |
| [`docs/chargeback-refund-protocol.md`](docs/chargeback-refund-protocol.md) | Chargeback pipeline, refund engine, credit/debit memos |
| [`docs/dispute-resolution-protocol.md`](docs/dispute-resolution-protocol.md) | 5-phase dispute lifecycle, automated assessment, human arbitration |
| [`docs/settlement-operations.md`](docs/settlement-operations.md) | Partial capture, split/batch/installment settlement, fee engine, FX, DLQ |
| [`docs/reporting-compliance-exports.md`](docs/reporting-compliance-exports.md) | Statements, compliance audit exports, transaction analytics |
| [`docs/v1.6.5-validation-report.md`](docs/v1.6.5-validation-report.md) | 284 tests, 8 bugs found and fixed |

---

## References

- [Google A2A Protocol](https://github.com/google/A2A) — Base agent-to-agent communication protocol
- [Stripe Connect](https://stripe.com/connect) — Multi-party payment infrastructure
- [OFAC SDN List](https://sanctionssearch.ofac.treas.gov/) — US sanctions screening
- [FATF Recommendations](https://www.fatf-gafi.org/recommendations.html) — AML/CFT standards
- [ISO 20022](https://www.iso20022.org/) — Financial messaging standard

---

## White Paper

The full white paper is available at https://a2a.tfsfventures.com and covers the protocol rationale, threat model, formal verification approach, and economic analysis of escrow mechanisms.

---

## Security

Found a vulnerability? See [`SECURITY.md`](SECURITY.md) for reporting instructions.

---

## License

This project is licensed under the Apache License 2.0 — see [`LICENSE`](LICENSE) for details.

---

<div align="center">

**Built by [TFSF Ventures FZ-LLC](https://tfsfventures.com)**

RAKEZ License 47013955 | Ras Al Khaimah, UAE

Built by [TFSF Ventures](https://tfsfventures.com).

---

Copyright 2026 TFSF Ventures FZ-LLC. All rights reserved.

</div>

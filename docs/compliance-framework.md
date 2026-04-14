# Compliance Framework

Version: 4.17.0 | Protocol: A2A Payment Protocol | Engine: Pulse Engines

---

## Overview

The Pulse Engines compliance framework is embedded directly in the payment
authorization pipeline. Every autonomous agent-to-agent transaction passes through
a Predictive Compliance engine before funds move. Compliance is not a post-hoc
audit layer -- it is a blocking gate in the authorization flow that evaluates
regulatory risk in real time across multiple jurisdictions simultaneously.

---

## Position in the Authorization Pipeline

Compliance evaluation occurs at Step 9 of the 12-step authorization pipeline.
The preceding steps handle authentication, policy lookup, spending limit checks,
counterparty validation, and wallet balance verification. Only transactions that
pass Steps 1-8 reach the compliance engine.

### Authorization Pipeline Overview

```
Step 1:  Receive payment request via /pulse-api/payments/request
Step 2:  Validate request schema and required fields
Step 3:  Authenticate requesting agent identity
Step 4:  Load applicable spending policy (org default or agent-specific)
Step 5:  Check per-transaction amount limit
Step 6:  Check daily aggregate spending limit
Step 7:  Check monthly aggregate spending limit
Step 8:  Validate counterparty (approved/blocked lists)
Step 9:  >>> COMPLIANCE PRECHECK <<< (this document)
Step 10: Human-in-the-loop escalation (if require_human_above threshold met)
Step 11: Record authorization decision with immutable proof
Step 12: Initiate settlement or escrow hold
```

### Step 9: compliance_precheck Message

When the authorization pipeline reaches Step 9, it sends a `compliance_precheck`
message to the Predictive Compliance engine:

```json
{
  "message_type": "compliance_precheck",
  "transaction_id": "txn_9f8e7d6c5b4a",
  "requesting_agent_id": "agent-treasury-ops",
  "requesting_org_id": "org_abc123",
  "counterparty_agent_id": "agent-vendor-pay",
  "counterparty_org_id": "org_def456",
  "amount": 25000.00,
  "currency": "USD",
  "tx_type": "vendor_payment",
  "category": "operations",
  "jurisdictions": ["US_FEDERAL", "US_STATE_NY", "EU_GDPR"],
  "metadata": {
    "invoice_id": "INV-2026-0412",
    "po_number": "PO-8834"
  },
  "policy_context": {
    "compliance_precheck": true,
    "compliance_jurisdictions": ["US_FEDERAL", "US_STATE_NY", "EU_GDPR"],
    "org_vertical": "real_estate",
    "org_tier": "enterprise"
  }
}
```

The compliance engine must respond within 2000ms. If it times out, the transaction
is held in `pending_compliance` state and retried up to 3 times with exponential
backoff (500ms, 1000ms, 2000ms). After 3 failures, the transaction is denied with
reason code `compliance_unavailable`.

---

## Multi-Source Scanning

The Predictive Compliance engine evaluates transactions against three parallel
data streams. All three complete before a verdict is returned.

### 1. Real-Time Regulatory Intelligence

Live feeds from regulatory bodies are continuously ingested and indexed:

- Federal Register (US) - New rules, proposed rules, final rules
- Official Journal of the European Union - Directives, regulations, decisions
- Central Bank of the UAE - Circulars, guidance notes, standards
- FinCEN Advisories - Suspicious activity alerts, geographic targeting orders
- FATF Mutual Evaluations - Country risk assessments

The intelligence feed is refreshed every 15 minutes. When a new regulation is
published, it is parsed, classified by jurisdiction and topic, and made available
to the compliance engine within one refresh cycle.

### 2. Historical Pattern Analysis

The engine maintains a rolling window of transaction patterns per agent, per org,
and per counterparty. Patterns analyzed include:

- Velocity anomalies (sudden increase in transaction frequency)
- Amount clustering (structuring detection around reporting thresholds)
- Counterparty concentration (excessive transactions with a single party)
- Geographic anomalies (transactions inconsistent with declared jurisdiction)
- Temporal patterns (unusual timing such as outside business hours)
- Category drift (agent transacting outside its normal categories)

Historical analysis uses a 90-day rolling window with exponential decay weighting.
Recent transactions carry more significance than older ones.

### 3. Cross-Jurisdictional Mapping

When a transaction spans multiple jurisdictions (e.g., a US-based agent paying an
EU-based counterparty), the engine maps regulatory requirements from all applicable
jurisdictions and evaluates the union of all constraints.

Cross-jurisdictional mapping handles:

- Conflicting requirements between jurisdictions (most restrictive rule applies)
- Reciprocity agreements (e.g., EU adequacy decisions for data transfer)
- Treaty obligations affecting financial transactions
- Extraterritorial reach (e.g., OFAC sanctions apply regardless of location)
- Reporting thresholds that differ by jurisdiction

---

## Jurisdiction Coverage

### US Federal

| Regulation   | Coverage                                                          |
| ------------ | ----------------------------------------------------------------- |
| BSA          | Bank Secrecy Act: CTR thresholds ($10K), SAR filing triggers,     |
|              | record-keeping requirements for agent-to-agent transactions       |
| Dodd-Frank   | Title VII: swap reporting applicability for certain tx types,     |
|              | Volcker Rule implications for proprietary agent transactions      |
| CFPB         | Consumer Financial Protection Bureau: disclosure requirements     |
|              | when agents interact with consumer-facing payment flows,          |
|              | error resolution procedures, unauthorized transfer protections    |
| OFAC         | Office of Foreign Assets Control: SDN list screening for all      |
|              | counterparty agents and their associated organizations,           |
|              | sectoral sanctions checks, geographic embargo verification,       |
|              | 50% rule for entity ownership chains                              |

### US State

| Area                 | Coverage                                                    |
| -------------------- | ----------------------------------------------------------- |
| Money Transmitter    | State-by-state licensing requirements evaluated when agent   |
|                      | transactions meet the definition of money transmission.      |
|                      | Covers all 50 states plus DC, PR, USVI. Exemption analysis  |
|                      | for bank-partner models and authorized delegate structures.  |
| Consumer Protection  | State-specific consumer protection statutes applied when     |
|                      | transactions involve consumer-facing agents. Includes        |
|                      | California CCPA/CPRA data handling, New York BitLicense      |
|                      | digital asset requirements, and state usury law compliance.  |

### European Union

| Regulation | Coverage                                                          |
| ---------- | ----------------------------------------------------------------- |
| GDPR       | Data protection impact assessment for transaction metadata.       |
|            | Lawful basis verification for processing payment data.            |
|            | Cross-border data transfer checks (adequacy, SCCs, BCRs).        |
|            | Data minimization validation on transaction payloads.             |
| PSD2       | Payment Services Directive 2: strong customer authentication      |
|            | requirements mapped to agent authentication steps. Open banking   |
|            | API compliance for agent-initiated payments. Transaction          |
|            | monitoring and fraud detection thresholds.                        |
| MiCA       | Markets in Crypto-Assets Regulation: asset classification when    |
|            | agent transactions involve digital asset denominations.           |
|            | Stablecoin reserve and redemption requirements. Whitepaper        |
|            | disclosure obligations for crypto-asset service providers.        |
| DORA       | Digital Operational Resilience Act: ICT risk management           |
|            | framework compliance for the Pulse Engines platform itself.       |
|            | Third-party ICT service provider oversight. Incident              |
|            | reporting requirements for operational disruptions.               |

### United Arab Emirates

| Authority | Coverage                                                           |
| --------- | ------------------------------------------------------------------ |
| CBUAE     | Central Bank of the UAE: stored value facility licensing,           |
|           | retail payment service provider requirements, AML/CFT              |
|           | framework compliance, large value payment system rules,            |
|           | agent-based service regulations.                                   |
| DFSA      | Dubai Financial Services Authority (DIFC): authorization           |
|           | requirements for financial services within the DIFC free zone,     |
|           | prudential requirements, conduct of business rules,                |
|           | anti-money laundering module compliance.                           |
| ADGM      | Abu Dhabi Global Market: financial services permissions,            |
|           | RegLab (sandbox) eligibility for experimental agent flows,         |
|           | virtual asset regulatory framework, capital adequacy.              |

### Latin America

| Regulation | Coverage                                                          |
| ---------- | ----------------------------------------------------------------- |
| LGPD       | Lei Geral de Protecao de Dados (Brazil): data protection          |
|            | requirements analogous to GDPR but with Brazilian-specific        |
|            | provisions. ANPD guidance on automated decision-making.           |
|            | Cross-border data transfer restrictions and adequacy.             |
| BCB        | Banco Central do Brasil: PIX instant payment system compliance,   |
|            | payment institution licensing categories, foreign exchange        |
|            | regulations for cross-border agent transactions, open finance     |
|            | framework integration requirements.                               |
| CNBV       | Comision Nacional Bancaria y de Valores (Mexico): fintech law     |
|            | (Ley Fintech) compliance for electronic payment fund              |
|            | institutions, virtual asset regulations, AML/CFT reporting        |
|            | through the PLD framework, API-based open finance rules.          |

---

## Compliance Result Schema

The Predictive Compliance engine returns a structured result within the 2000ms
timeout window:

```json
{
  "status": "clear",
  "jurisdictions_checked": [
    "US_FEDERAL_BSA",
    "US_FEDERAL_OFAC",
    "US_STATE_NY_MTL",
    "EU_GDPR",
    "EU_PSD2"
  ],
  "findings": [],
  "confidence_score": 0.97,
  "processing_time_ms": 342
}
```

### Status Values

| Status    | Meaning                                                           |
| --------- | ----------------------------------------------------------------- |
| `clear`   | No compliance issues found. Transaction may proceed.              |
| `flagged` | Non-blocking findings detected. Transaction proceeds but          |
|           | findings are attached to the authorization record for review.     |
| `blocked` | Blocking compliance issue detected. Transaction is denied.        |
| `error`   | Compliance engine encountered an error during evaluation.         |

### Findings Array

When `status` is `flagged` or `blocked`, the `findings` array contains one or
more finding objects:

```json
{
  "findings": [
    {
      "finding_id": "fnd_a1b2c3",
      "jurisdiction": "US_FEDERAL_OFAC",
      "severity": "critical",
      "category": "sanctions",
      "description": "Counterparty organization matches SDN list entry",
      "regulation_reference": "31 CFR Part 501",
      "recommended_action": "block_transaction",
      "evidence": {
        "matched_entity": "Entity Name LLC",
        "match_score": 0.94,
        "list_entry_date": "2025-11-15"
      }
    }
  ]
}
```

### Finding Severity Levels

| Severity   | Impact                                                        |
| ---------- | ------------------------------------------------------------- |
| `critical` | Automatically blocks the transaction. No override possible.   |
| `high`     | Blocks unless the policy explicitly sets an override flag.     |
| `medium`   | Flags the transaction. Proceeds but appears in audit reports.  |
| `low`      | Informational. Logged but does not affect authorization.       |

### Confidence Score

The `confidence_score` (0.0 to 1.0) indicates the engine's certainty in its
evaluation. Scores below 0.80 trigger automatic human review escalation regardless
of the compliance status. The score factors in:

- Data freshness (time since last regulatory feed update)
- Entity resolution confidence (name matching accuracy)
- Jurisdiction coverage completeness
- Historical pattern data availability

---

## Immutable Proof in Authorization Record

Every compliance evaluation result is permanently embedded in the authorization
record. This creates an immutable audit trail that links each transaction to the
exact compliance state at the time of authorization.

### Authorization Record Structure

```json
{
  "authorization_id": "auth_x1y2z3",
  "transaction_id": "txn_9f8e7d6c5b4a",
  "decision": "approved",
  "compliance_result": {
    "status": "clear",
    "jurisdictions_checked": ["US_FEDERAL_BSA", "US_FEDERAL_OFAC", "EU_GDPR"],
    "findings": [],
    "confidence_score": 0.97,
    "processing_time_ms": 342,
    "engine_version": "2026.04.01",
    "regulatory_feed_timestamp": "2026-04-14T12:30:00.000Z"
  },
  "policy_snapshot": {
    "policy_id": "pol_abc123",
    "max_per_transaction": 50000,
    "compliance_precheck": true,
    "compliance_jurisdictions": ["US_FEDERAL", "US_STATE_NY", "EU_GDPR"]
  },
  "created_at": "2026-04-14T12:34:57.000Z"
}
```

### Immutability Guarantees

- Authorization records are stored in an append-only table.
- No UPDATE or DELETE operations are permitted on the table.
- Row-level security prevents modification by any role including service roles.
- Each record includes a SHA-256 hash of its contents for tamper detection.
- Records are retained for a minimum of 7 years per BSA requirements.

---

## Post-Transaction Compliance

After settlement, the Auditor engine sends a compliance review request to the
Predictive Compliance engine for post-transaction analysis.

### Auditor to Compliance Engine Flow

```
Settlement Complete
    |
    v
Auditor Engine (scheduled, runs hourly)
    |
    v
compliance_review message to Predictive Compliance Engine
    |
    v
Post-transaction findings attached to transaction record
    |
    v
Alert generated if post-transaction findings differ from pre-transaction
```

### Post-Transaction Review Message

```json
{
  "message_type": "compliance_review",
  "transaction_id": "txn_9f8e7d6c5b4a",
  "review_type": "post_settlement",
  "settlement_timestamp": "2026-04-14T12:35:00.000Z",
  "original_compliance_result": {
    "status": "clear",
    "confidence_score": 0.97
  }
}
```

### Divergence Detection

If the post-transaction compliance review produces a different `status` than the
pre-transaction check (e.g., a sanctions list was updated between authorization
and the hourly audit run), the system:

1. Generates a `compliance.divergence` alert event.
2. Flags the transaction for manual review.
3. If the new status is `blocked`, initiates a hold on the counterparty agent wallet.
4. Notifies the org administrator via webhook (`compliance.review_required` event).

---

## Adding New Jurisdictions

Adding support for a new jurisdiction is a configuration-only operation that does
not require code changes or redeployment.

### Configuration Steps

1. **Add jurisdiction definition** to the jurisdictions configuration table:

```json
{
  "jurisdiction_code": "SG_MAS",
  "display_name": "Singapore - Monetary Authority of Singapore",
  "region": "APAC",
  "regulatory_bodies": ["MAS"],
  "applicable_regulations": [
    "Payment Services Act 2019",
    "MAS Notice PSN01",
    "MAS Notice PSN02"
  ],
  "reporting_thresholds": {
    "ctr_threshold": 20000,
    "ctr_currency": "SGD"
  },
  "active": true
}
```

2. **Configure regulatory feed source** for the new jurisdiction in the
   intelligence feed settings.

3. **Map regulation rules** to the compliance rule engine using the declarative
   rule format:

```json
{
  "rule_id": "SG_MAS_PSA_001",
  "jurisdiction": "SG_MAS",
  "regulation": "Payment Services Act 2019",
  "condition": "amount >= 5000 AND currency = 'SGD'",
  "action": "flag",
  "severity": "medium",
  "description": "Transaction exceeds enhanced due diligence threshold"
}
```

4. **Assign jurisdiction to organizations** via the spending policy
   `compliance_jurisdictions` array.

### No-Code Deployment

Because jurisdiction rules are evaluated dynamically from configuration, adding
Singapore MAS support (or any other jurisdiction) requires:

- Zero code changes
- Zero service endpoint redeployments
- Zero downtime
- Immediate availability after configuration insert

The compliance engine loads jurisdiction rules on each evaluation, ensuring new
rules are active within one evaluation cycle of being configured.

---

## Compliance Monitoring and Reporting

### Real-Time Dashboard Metrics

The compliance engine exposes the following metrics through the
`/pulse-api/reports/compliance` endpoint:

- Transactions scanned per hour / day / month
- Clear / flagged / blocked ratio over time
- Average processing time by jurisdiction count
- Confidence score distribution
- Top finding categories
- Jurisdiction coverage map

### Regulatory Reporting

The platform generates jurisdiction-specific regulatory reports:

- **BSA/FinCEN**: Automated CTR generation for transactions exceeding $10,000
- **OFAC**: Blocked transaction reports with SDN match details
- **GDPR**: Data processing activity records (Article 30)
- **PSD2**: Strong authentication compliance reports
- **CBUAE**: Suspicious Transaction Report (STR) generation

All reports are generated in the format required by the respective regulatory body
and include the immutable authorization record as supporting evidence.

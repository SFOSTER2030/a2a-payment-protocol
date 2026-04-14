# Reporting, Compliance, and Exports

Version: 2.1.0
Status: Production
Last Updated: 2026-04-14

---

## Statement Generation

### What a Statement Contains

Statements are the financial record of an organization's or agent's activity over a defined period. They exist because auditors, finance teams, and compliance officers need a single document that tells the complete story of money movement -- not just transactions, but the context around them.

A statement includes:

- **Opening balance**: The wallet balance at the start of the statement period, broken down by currency.
- **Transactions**: Every payment authorized, settled, refunded, or cancelled during the period, with counterparty details, settlement mode, and timestamps.
- **Fees**: All fees charged during the period, broken down by fee type (platform, processing, escrow, cross-org), with references to the payments that generated them.
- **Escrow activity**: Escrows opened, settled, cancelled, and disputed during the period. Includes duration, resolution outcome, and any fees accrued.
- **Reconciliation summary**: Match rate between platform records and counterparty records. Discrepancies are flagged with reference IDs.
- **Chargebacks and disputes**: Any chargebacks filed against the org's transactions, their current status, and resolution outcomes.
- **Memos**: Operational notes attached to transactions by agents or compliance officers during the period. These provide human-readable context that structured data cannot capture.
- **Closing balance**: The wallet balance at the end of the statement period, with a reconciliation check against opening balance + credits - debits.

### Generating a Statement

```
GET https://{your-instance}.pulse-internal/api/pulse-api/statements?scope=org&scope_id=org_42&period=2026-03&format=json
Authorization: Bearer {token}
```

Query parameters:

| Parameter | Required | Values | Description |
|---|---|---|---|
| `scope` | Yes | `org`, `agent`, `wallet` | What entity the statement covers |
| `scope_id` | Yes | Entity ID | The specific org, agent, or wallet |
| `period` | Yes | `YYYY-MM` or `YYYY-Q1` through `YYYY-Q4` or custom range | Statement period |
| `format` | No | `json`, `pdf`, `csv` | Output format. Default `json` |
| `include_memos` | No | `true`, `false` | Include operational memos. Default `true` |
| `include_pending` | No | `true`, `false` | Include pending/authorized transactions. Default `false` |

For custom date ranges:

```
GET https://{your-instance}.pulse-internal/api/pulse-api/statements?scope=org&scope_id=org_42&date_from=2026-01-01&date_to=2026-03-31&format=pdf
Authorization: Bearer {token}
```

### JSON Response Structure

```json
{
  "statement_id": "stmt_org42_202603",
  "scope": "org",
  "scope_id": "org_42",
  "period": {
    "from": "2026-03-01T00:00:00Z",
    "to": "2026-03-31T23:59:59Z"
  },
  "opening_balances": {
    "USD": 5000000,
    "EUR": 1200000
  },
  "transactions": {
    "total_count": 8472,
    "settled_count": 8310,
    "refunded_count": 87,
    "cancelled_count": 75,
    "total_debits": 42150000,
    "total_credits": 39870000,
    "by_settlement_mode": {
      "instant": { "count": 6200, "amount": 31000000 },
      "escrow": { "count": 1800, "amount": 9000000 },
      "external": { "count": 472, "amount": 2150000 }
    }
  },
  "fees": {
    "platform_fee_total": 632250,
    "processing_fee_total": 211800,
    "escrow_fee_total": 45000,
    "cross_org_fee_total": 23600,
    "fee_grand_total": 912650
  },
  "escrow_activity": {
    "opened": 1800,
    "settled": 1720,
    "cancelled": 65,
    "disputed": 15,
    "average_duration_hours": 36.4,
    "total_escrowed_amount": 9000000,
    "total_escrow_fees": 45000
  },
  "reconciliation": {
    "match_rate_percent": 99.87,
    "matched_count": 8461,
    "discrepancy_count": 11,
    "discrepancy_amount": 3200,
    "discrepancy_refs": ["disc_001", "disc_002", "disc_003"]
  },
  "chargebacks": {
    "filed": 5,
    "won": 3,
    "lost": 1,
    "pending": 1,
    "total_chargeback_amount": 75000,
    "chargeback_rate_percent": 0.06
  },
  "memos": [
    {
      "memo_id": "memo_001",
      "payment_id": "pay_flagged_042",
      "author": "compliance_officer_02",
      "timestamp": "2026-03-15T14:30:00Z",
      "text": "Manual review completed. Transaction cleared."
    }
  ],
  "closing_balances": {
    "USD": 2720000,
    "EUR": 1200000
  },
  "balance_check": {
    "USD": {
      "opening": 5000000,
      "credits": 39870000,
      "debits": 42150000,
      "expected_closing": 2720000,
      "actual_closing": 2720000,
      "balanced": true
    },
    "EUR": {
      "opening": 1200000,
      "credits": 0,
      "debits": 0,
      "expected_closing": 1200000,
      "actual_closing": 1200000,
      "balanced": true
    }
  },
  "generated_at": "2026-04-01T02:00:00Z"
}
```

### PDF Statements with Org Branding

PDF statements include the organization's logo, legal name, registration details, and contact information. Branding is configured per org:

```
PATCH https://{your-instance}.pulse-internal/api/pulse-api/orgs/{org_id}/statement-config
Content-Type: application/json
Authorization: Bearer {token}

{
  "branding": {
    "logo_url": "https://assets.example-org.com/logo-dark.png",
    "legal_name": "Meridian Data Exchange Ltd.",
    "registration_number": "REG-2024-UK-78451",
    "address_line_1": "45 Canary Wharf Tower",
    "address_line_2": "London E14 5AB, United Kingdom",
    "contact_email": "finance@meridian-exchange.example.com"
  },
  "pdf_options": {
    "include_transaction_detail": true,
    "include_fee_breakdown": true,
    "include_reconciliation_appendix": true,
    "page_size": "A4",
    "language": "en"
  }
}
```

The PDF renderer produces a document with cover page, summary tables, transaction listing, fee appendix, reconciliation appendix, and a signed hash footer for integrity verification.

### Scheduled Statement Delivery

Statements can be generated and delivered automatically on a schedule:

```
POST https://{your-instance}.pulse-internal/api/pulse-api/orgs/{org_id}/statement-schedule
Content-Type: application/json
Authorization: Bearer {token}

{
  "frequency": "monthly",
  "generate_on_day": 1,
  "generate_at_hour": 2,
  "format": "pdf",
  "delivery_method": "webhook",
  "webhook_url": "https://finance.meridian-exchange.example.com/incoming/statements",
  "recipients": [
    { "type": "email", "address": "cfo@meridian-exchange.example.com" },
    { "type": "webhook", "url": "https://erp.meridian-exchange.example.com/api/ingest/statements" }
  ],
  "retention_days": 2555
}
```

The `retention_days` field controls how long generated statements are stored on the platform. The default is 2555 days (7 years), which aligns with most financial record retention requirements.

---

## Compliance Audit Export

### Why Compliance Exports Are Separate from Statements

Statements are for finance. Compliance exports are for regulators. The distinction matters because regulatory exports have requirements that go far beyond what a financial statement provides:

- Specific data fields mandated by each jurisdiction's regulator
- Specific file formats (often XML or fixed-width, not JSON or PDF)
- Immutability guarantees (the export cannot be modified after generation)
- Chain of custody documentation (who requested it, when, why, who accessed it)
- Retention rules that may differ from financial record retention

A statement shows what happened. A compliance export proves what happened, in the exact format the regulator expects, with cryptographic integrity guarantees.

### Initiating a Compliance Export

```
POST https://{your-instance}.pulse-internal/api/pulse-api/compliance/export
Content-Type: application/json
Authorization: Bearer {token}

{
  "org_id": "org_42",
  "jurisdiction": "US",
  "regulation": "FinCEN_CTR",
  "date_range": {
    "from": "2026-01-01",
    "to": "2026-03-31"
  },
  "format": "xml",
  "export_reason": "quarterly_filing",
  "requested_by": "compliance_officer_07",
  "include_supporting_evidence": true,
  "encryption": {
    "method": "AES-256-GCM",
    "recipient_public_key_id": "key_compliance_07"
  }
}
```

The `include_supporting_evidence` flag attaches the underlying transaction records, KYC verification results, and risk assessment outputs to the export. This creates a self-contained package that regulators can review without requesting additional data.

### Jurisdiction-Specific Export Formats

#### United States: SAR and FinCEN

For US operations, the platform supports two primary export types:

**Suspicious Activity Report (SAR):** Generated when Pulse Engines' risk scoring flags transactions that meet SAR filing thresholds. The export conforms to FinCEN's BSA E-Filing XML schema.

```json
{
  "export_type": "SAR",
  "regulation": "FinCEN_SAR",
  "format": "xml",
  "schema_version": "1.5",
  "filing_fields": {
    "filing_type": "initial",
    "activity_type": "structuring",
    "suspicious_amount_total": 4500000,
    "date_range_of_activity": {
      "from": "2026-02-01",
      "to": "2026-02-28"
    },
    "subject_count": 2,
    "transaction_count": 47
  }
}
```

**Currency Transaction Report (CTR):** Automatically generated for transactions exceeding $10,000 in a single day. The export batches all qualifying transactions for the filing period.

```json
{
  "export_type": "CTR",
  "regulation": "FinCEN_CTR",
  "format": "xml",
  "schema_version": "2.0",
  "qualifying_transactions": 23,
  "total_amount": 892000,
  "period": "2026-Q1"
}
```

#### European Union: PSD2 and DORA

**PSD2 (Payment Services Directive 2):** Strong Customer Authentication (SCA) compliance records, transaction monitoring reports, and third-party provider access logs.

```json
{
  "export_type": "PSD2_compliance",
  "regulation": "PSD2",
  "format": "xml",
  "schema_version": "3.1",
  "sca_records": {
    "total_transactions": 12500,
    "sca_applied": 12480,
    "sca_exemptions": 20,
    "exemption_types": {
      "low_value": 12,
      "trusted_beneficiary": 5,
      "recurring": 3
    }
  }
}
```

**DORA (Digital Operational Resilience Act):** ICT risk management reports, incident logs, and third-party dependency documentation. DORA exports focus on operational resilience rather than transaction data.

```json
{
  "export_type": "DORA_compliance",
  "regulation": "DORA",
  "format": "json",
  "schema_version": "1.0",
  "ict_risk_assessment": {
    "period": "2026-Q1",
    "critical_systems": 4,
    "incidents_reported": 1,
    "mean_time_to_recovery_minutes": 12,
    "third_party_dependencies": 7,
    "third_party_risk_reviews_completed": 7
  }
}
```

#### UAE: CBUAE and DFSA

**CBUAE (Central Bank of the UAE):** Anti-money laundering (AML) reports, large transaction reports, and sanctions screening results for entities operating under the central bank's jurisdiction.

```json
{
  "export_type": "CBUAE_AML",
  "regulation": "CBUAE_AML",
  "format": "xml",
  "schema_version": "2.3",
  "aml_records": {
    "total_screened": 9800,
    "sanctions_hits": 0,
    "pep_matches": 3,
    "pep_cleared": 3,
    "large_transaction_reports": 15,
    "threshold_aed": 5500000
  }
}
```

**DFSA (Dubai Financial Services Authority):** For entities in the DIFC, the export includes prudential reporting, conduct-of-business records, and client money reconciliation.

```json
{
  "export_type": "DFSA_prudential",
  "regulation": "DFSA",
  "format": "xml",
  "schema_version": "4.0",
  "prudential_report": {
    "capital_adequacy_ratio": 15.2,
    "client_money_segregated": true,
    "client_money_reconciliation_frequency": "daily",
    "reconciliation_discrepancies": 0
  }
}
```

#### Latin America: BCB and LGPD

**BCB (Banco Central do Brasil):** PIX transaction reports, instant payment monitoring, and mandatory central bank filings for entities operating in Brazil.

```json
{
  "export_type": "BCB_reporting",
  "regulation": "BCB_PIX",
  "format": "xml",
  "schema_version": "3.2",
  "pix_records": {
    "total_pix_transactions": 45000,
    "total_pix_amount_brl": 12500000,
    "fraud_reports_filed": 2,
    "chargeback_requests": 8,
    "average_settlement_seconds": 1.2
  }
}
```

**LGPD (Lei Geral de Protecao de Dados):** Data protection compliance export. Documents all personal data processing activities, consent records, and data subject access requests (DSARs) handled during the period.

```json
{
  "export_type": "LGPD_compliance",
  "regulation": "LGPD",
  "format": "json",
  "schema_version": "1.1",
  "data_protection": {
    "processing_activities_documented": 14,
    "consent_records": 3200,
    "dsar_received": 5,
    "dsar_completed": 5,
    "dsar_average_response_days": 3,
    "data_breaches": 0,
    "dpo_contact": "dpo@meridian-exchange.example.com"
  }
}
```

### Immutable Export with SHA-256 Hash

Every compliance export is immutable once generated. The export payload is hashed with SHA-256, and the hash is recorded in the platform's append-only audit log. If the export file is later modified, the hash will not match and the tampering will be detectable.

```json
{
  "export_id": "cexp_us_fincen_2026q1_org42",
  "status": "completed",
  "generated_at": "2026-04-01T03:00:00Z",
  "file_size_bytes": 284672,
  "integrity": {
    "algorithm": "SHA-256",
    "hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "hash_recorded_at": "2026-04-01T03:00:01Z",
    "hash_recorded_in": "audit_log_block_28847"
  },
  "encryption": {
    "method": "AES-256-GCM",
    "encrypted_for": "compliance_officer_07"
  }
}
```

To verify an export's integrity after download:

```
GET https://{your-instance}.pulse-internal/api/pulse-api/compliance/export/{export_id}/verify
Authorization: Bearer {token}

{
  "provided_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
}
```

```json
{
  "export_id": "cexp_us_fincen_2026q1_org42",
  "verification_result": "match",
  "original_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "provided_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "verified_at": "2026-04-14T10:00:00Z"
}
```

### Chain of Custody

The chain of custody record tracks every access to a compliance export. This is required by several regulatory frameworks and ensures accountability.

```
GET https://{your-instance}.pulse-internal/api/pulse-api/compliance/export/{export_id}/custody
Authorization: Bearer {token}
```

```json
{
  "export_id": "cexp_us_fincen_2026q1_org42",
  "custody_chain": [
    {
      "event": "export.requested",
      "actor": "compliance_officer_07",
      "timestamp": "2026-04-01T02:55:00Z",
      "ip_address": "10.0.42.15",
      "reason": "quarterly_filing"
    },
    {
      "event": "export.generated",
      "actor": "system",
      "timestamp": "2026-04-01T03:00:00Z",
      "details": "Export generated, SHA-256 hash recorded"
    },
    {
      "event": "export.downloaded",
      "actor": "compliance_officer_07",
      "timestamp": "2026-04-01T09:15:00Z",
      "ip_address": "10.0.42.15"
    },
    {
      "event": "export.shared",
      "actor": "compliance_officer_07",
      "timestamp": "2026-04-02T11:00:00Z",
      "shared_with": "external_auditor_deloitte",
      "method": "secure_transfer_portal"
    },
    {
      "event": "export.submitted",
      "actor": "compliance_officer_07",
      "timestamp": "2026-04-05T14:30:00Z",
      "submitted_to": "FinCEN_efile",
      "confirmation_number": "FCN-2026-Q1-884721"
    }
  ]
}
```

---

## Transaction Analytics

### Overview

The analytics endpoint provides real-time and historical metrics across every dimension of payment activity. These metrics feed dashboards, alerting systems, and executive reports. The design principle is that any question an operations team, finance team, or compliance team might ask about payment activity should be answerable from the analytics API without querying raw transaction data.

### Querying Analytics

```
GET https://{your-instance}.pulse-internal/api/pulse-api/analytics?org_id=org_42&period=2026-03&granularity=daily
Authorization: Bearer {token}
```

Query parameters:

| Parameter | Required | Values | Description |
|---|---|---|---|
| `org_id` | Yes | Org ID | Organization to query |
| `period` | No | `YYYY-MM`, `YYYY-QN`, `YYYY`, or custom range | Default: current month |
| `date_from` | No | ISO date | Start of custom range |
| `date_to` | No | ISO date | End of custom range |
| `granularity` | No | `hourly`, `daily`, `weekly`, `monthly` | Time bucket size. Default `daily` |
| `agent_id` | No | Agent ID | Filter to specific agent |
| `vertical` | No | String | Filter to business vertical |
| `jurisdiction` | No | ISO country code | Filter to jurisdiction |
| `currency` | No | ISO currency code | Filter to currency |

### Metric Categories

#### Volume Metrics

Transaction volume is the most basic and most important metric. It tells you how much money moved through the platform.

```json
{
  "volume": {
    "total_transactions": 84720,
    "total_amount": 421500000,
    "average_transaction_amount": 4975,
    "median_transaction_amount": 2500,
    "p95_transaction_amount": 15000,
    "p99_transaction_amount": 50000,
    "daily_breakdown": [
      {
        "date": "2026-03-01",
        "transaction_count": 2734,
        "total_amount": 13600000
      },
      {
        "date": "2026-03-02",
        "transaction_count": 2891,
        "total_amount": 14450000
      }
    ]
  }
}
```

#### Settlement Mode Distribution

Understanding how payments settle reveals operational patterns. A spike in escrow usage might indicate that agents are dealing with untrusted counterparties. A drop in instant settlement might signal wallet balance issues.

```json
{
  "settlement_mode_distribution": {
    "instant": {
      "count": 62000,
      "amount": 310000000,
      "percentage_by_count": 73.2,
      "percentage_by_amount": 73.5
    },
    "escrow": {
      "count": 18000,
      "amount": 90000000,
      "percentage_by_count": 21.2,
      "percentage_by_amount": 21.4
    },
    "external": {
      "count": 4720,
      "amount": 21500000,
      "percentage_by_count": 5.6,
      "percentage_by_amount": 5.1
    }
  }
}
```

#### Escrow Resolution Metrics

Escrow metrics matter because unresolved escrows are capital tied up in limbo. High dispute rates signal friction in agent-to-agent commerce.

```json
{
  "escrow_resolution": {
    "opened": 18000,
    "settled": 17200,
    "cancelled": 650,
    "disputed": 150,
    "timed_out": 0,
    "settlement_rate_percent": 95.56,
    "dispute_rate_percent": 0.83,
    "average_resolution_hours": 36.4,
    "median_resolution_hours": 12.0,
    "p95_resolution_hours": 168.0,
    "total_escrowed_amount": 90000000,
    "average_escrow_amount": 5000
  }
}
```

#### Chargeback, Refund, and Dispute Rates

These are the metrics that payment processors and regulators watch most closely. High chargeback rates can result in fines, increased processing fees, or termination of payment processing privileges.

```json
{
  "chargebacks": {
    "filed": 50,
    "won": 30,
    "lost": 12,
    "pending": 8,
    "chargeback_rate_percent": 0.059,
    "win_rate_percent": 71.43,
    "total_chargeback_amount": 750000,
    "average_chargeback_amount": 15000,
    "trend": "stable"
  },
  "refunds": {
    "total": 870,
    "refund_rate_percent": 1.03,
    "total_refund_amount": 4350000,
    "average_refund_amount": 5000,
    "full_refunds": 650,
    "partial_refunds": 220
  },
  "disputes": {
    "opened": 200,
    "resolved": 185,
    "escalated": 10,
    "pending": 5,
    "average_resolution_days": 4.2,
    "dispute_rate_percent": 0.24
  }
}
```

#### Processing Time Metrics

How fast are payments moving through the pipeline? Processing time breakdowns help identify bottlenecks.

```json
{
  "processing_times": {
    "authorization": {
      "p50_ms": 45,
      "p95_ms": 120,
      "p99_ms": 350,
      "max_ms": 2100
    },
    "settlement_instant": {
      "p50_ms": 80,
      "p95_ms": 200,
      "p99_ms": 500,
      "max_ms": 3200
    },
    "settlement_escrow_to_resolution": {
      "p50_hours": 12.0,
      "p95_hours": 168.0,
      "p99_hours": 336.0,
      "max_hours": 720.0
    },
    "settlement_external": {
      "p50_hours": 2.0,
      "p95_hours": 24.0,
      "p99_hours": 72.0,
      "max_hours": 120.0
    }
  }
}
```

#### Top Counterparties

Identifies the highest-volume counterparties by transaction count and amount. Useful for relationship management and risk concentration analysis.

```json
{
  "top_counterparties": {
    "by_amount": [
      {
        "counterparty_id": "org_vendor_alpha",
        "counterparty_name": "Alpha Data Services",
        "transaction_count": 4500,
        "total_amount": 85000000,
        "percentage_of_total_volume": 20.2
      },
      {
        "counterparty_id": "org_vendor_beta",
        "counterparty_name": "Beta Compute Network",
        "transaction_count": 12000,
        "total_amount": 60000000,
        "percentage_of_total_volume": 14.2
      },
      {
        "counterparty_id": "agent_marketplace_03",
        "counterparty_name": "Marketplace Agent 03",
        "transaction_count": 28000,
        "total_amount": 42000000,
        "percentage_of_total_volume": 10.0
      }
    ],
    "concentration_risk": {
      "top_1_percent_of_volume": 20.2,
      "top_5_percent_of_volume": 52.4,
      "herfindahl_index": 0.08
    }
  }
}
```

#### Category Distribution

Payments are categorized by the type of goods or services being exchanged. Category codes are assigned by the authorizing agent and validated against the org's allowed category list.

```json
{
  "category_distribution": [
    {
      "category_code": "DATA_PURCHASE",
      "category_name": "Data Purchase",
      "transaction_count": 35000,
      "total_amount": 175000000,
      "percentage": 41.5
    },
    {
      "category_code": "COMPUTE_CREDIT",
      "category_name": "Compute Credit",
      "transaction_count": 28000,
      "total_amount": 84000000,
      "percentage": 19.9
    },
    {
      "category_code": "API_ACCESS",
      "category_name": "API Access Fee",
      "transaction_count": 15000,
      "total_amount": 45000000,
      "percentage": 10.7
    },
    {
      "category_code": "CONSULTING",
      "category_name": "Agent Consulting Services",
      "transaction_count": 4000,
      "total_amount": 80000000,
      "percentage": 19.0
    },
    {
      "category_code": "OTHER",
      "category_name": "Other / Uncategorized",
      "transaction_count": 2720,
      "total_amount": 37500000,
      "percentage": 8.9
    }
  ]
}
```

#### Compliance Pass/Fail Rates

Every transaction passes through compliance checks (sanctions screening, PEP checks, velocity limits, spending policy validation). This metric shows how many transactions pass cleanly versus how many are flagged.

```json
{
  "compliance": {
    "total_screened": 84720,
    "passed": 84200,
    "flagged": 520,
    "blocked": 45,
    "pass_rate_percent": 99.39,
    "flag_rate_percent": 0.61,
    "block_rate_percent": 0.05,
    "flag_reasons": {
      "velocity_limit_exceeded": 200,
      "sanctions_near_match": 150,
      "spending_policy_violation": 100,
      "pep_match": 40,
      "jurisdiction_restriction": 30
    },
    "false_positive_rate_percent": 85.0,
    "average_review_time_hours": 2.4
  }
}
```

The false positive rate matters because it measures the operational burden of compliance screening. A high false positive rate means compliance officers are spending time reviewing transactions that turn out to be legitimate. Tuning the screening thresholds to reduce false positives without increasing false negatives is a continuous calibration exercise.

#### Reconciliation Match Rate

How well do platform records match counterparty records? A 100% match rate is the goal. Anything below 99.5% warrants investigation.

```json
{
  "reconciliation": {
    "total_reconciliation_records": 84720,
    "matched": 84610,
    "unmatched": 110,
    "match_rate_percent": 99.87,
    "unmatched_by_reason": {
      "amount_mismatch": 40,
      "timestamp_mismatch": 30,
      "missing_counterparty_record": 25,
      "duplicate_record": 10,
      "currency_mismatch": 5
    },
    "average_reconciliation_delay_hours": 1.2,
    "auto_reconciled_percent": 97.5,
    "manual_reconciled_percent": 2.5
  }
}
```

#### Dead Letter Queue Depth

DLQ depth is an operational health metric. A growing queue means payments are failing faster than they are being resolved. A stable near-zero queue means the operations team is keeping up.

```json
{
  "dlq": {
    "current_depth": 7,
    "current_total_amount": 185000,
    "oldest_entry_hours": 48,
    "entries_by_severity": {
      "warning": 4,
      "critical": 2,
      "escalation": 1
    },
    "resolution_rate_24h": 12,
    "average_resolution_hours": 6.3,
    "sla_compliance_percent": 92.0,
    "trend": "improving"
  }
}
```

#### Fee Revenue

For organizations that charge fees (marketplace operators, platform providers), fee revenue is a primary business metric.

```json
{
  "fee_revenue": {
    "total_fee_revenue": 9126500,
    "by_fee_type": {
      "platform_fee": 6322500,
      "processing_fee": 2118000,
      "escrow_fee": 450000,
      "cross_org_fee": 236000
    },
    "average_fee_per_transaction": 108,
    "fee_to_volume_ratio_percent": 2.17,
    "daily_fee_revenue": [
      { "date": "2026-03-01", "revenue": 295000 },
      { "date": "2026-03-02", "revenue": 310000 }
    ],
    "trend": "growing",
    "month_over_month_change_percent": 4.2
  }
}
```

### Breakdowns

Every metric category supports dimensional breakdowns. Breakdowns allow you to slice the data by:

- **Agent**: `?breakdown=agent` -- see metrics per agent within the org.
- **Organization**: `?breakdown=org` -- see metrics per org (platform-level queries only).
- **Vertical**: `?breakdown=vertical` -- see metrics per business vertical (data services, compute, consulting, etc.).
- **Settlement Mode**: `?breakdown=mode` -- see metrics per settlement mode (instant, escrow, external).
- **Transaction Type**: `?breakdown=type` -- see metrics per transaction type (purchase, refund, chargeback, transfer).
- **Jurisdiction**: `?breakdown=jurisdiction` -- see metrics per regulatory jurisdiction (US, EU, UAE, LATAM, etc.).

Multiple breakdowns can be combined:

```
GET https://{your-instance}.pulse-internal/api/pulse-api/analytics?org_id=org_42&period=2026-03&breakdown=agent,mode
Authorization: Bearer {token}
```

This returns metrics nested by agent and then by settlement mode within each agent. The response structure becomes:

```json
{
  "breakdowns": {
    "agent_compute_broker_14": {
      "instant": {
        "transaction_count": 15000,
        "total_amount": 75000000,
        "average_amount": 5000
      },
      "escrow": {
        "transaction_count": 3000,
        "total_amount": 15000000,
        "average_amount": 5000
      }
    },
    "agent_data_buyer_07": {
      "instant": {
        "transaction_count": 8000,
        "total_amount": 40000000,
        "average_amount": 5000
      },
      "escrow": {
        "transaction_count": 5000,
        "total_amount": 25000000,
        "average_amount": 5000
      }
    }
  }
}
```

### Real-Time vs. Historical Analytics

The analytics endpoint serves both real-time and historical queries. The distinction is controlled by the `mode` parameter:

- `mode=realtime` (default for current day): Queries the live transaction stream. Data may lag by up to 30 seconds. Best for dashboards and operational monitoring.
- `mode=historical` (default for past periods): Queries the pre-aggregated analytics store. Data is exact and reconciled. Best for reporting and compliance.

```
GET https://{your-instance}.pulse-internal/api/pulse-api/analytics?org_id=org_42&period=2026-03&mode=historical
```

Historical analytics are computed nightly by Pulse Engines' aggregation pipeline. The aggregation runs at 02:00 UTC and typically completes within 15 minutes for orgs with up to 1 million transactions per month. Larger orgs may require dedicated aggregation windows.

### Exporting Analytics

Analytics data can be exported for consumption by external BI tools:

```
POST https://{your-instance}.pulse-internal/api/pulse-api/analytics/export
Content-Type: application/json
Authorization: Bearer {token}

{
  "org_id": "org_42",
  "period": "2026-03",
  "metrics": ["volume", "settlement_mode_distribution", "fee_revenue", "compliance"],
  "format": "csv",
  "granularity": "daily",
  "delivery": {
    "method": "download_url",
    "url_expiry_hours": 24
  }
}
```

```json
{
  "export_id": "aexp_org42_202603",
  "status": "generating",
  "estimated_completion_seconds": 30,
  "poll_url": "https://{your-instance}.pulse-internal/api/pulse-api/analytics/export/aexp_org42_202603"
}
```

Once complete:

```json
{
  "export_id": "aexp_org42_202603",
  "status": "completed",
  "download_url": "https://{your-instance}.pulse-internal/api/pulse-api/analytics/export/aexp_org42_202603/download",
  "download_url_expires_at": "2026-04-15T10:00:00Z",
  "file_size_bytes": 1284672,
  "row_count": 31,
  "format": "csv",
  "generated_at": "2026-04-14T10:00:30Z"
}
```

Supported export formats:

| Format | Use Case |
|---|---|
| `csv` | General-purpose, spreadsheet-compatible |
| `json` | API consumption, programmatic processing |
| `parquet` | Data warehouse ingestion, columnar analytics |
| `xlsx` | Executive reporting with pre-formatted sheets |

The `parquet` format is particularly useful for organizations that ingest analytics into data lakes. Parquet files are columnar, compressed, and schema-aware, making them significantly more efficient for analytical queries than row-oriented formats like CSV or JSON.

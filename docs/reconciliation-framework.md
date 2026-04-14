# Reconciliation Framework

> A2A Payment Protocol -- Automated Audit, Anomaly Detection & Compliance Reporting

---

## 1. Overview

An agent paid $500 for a research report that was never delivered. Without reconciliation, nobody notices until a human audits the books -- which at 4,500 transactions per week across a fund, means never. The money is gone, the service is owed, and the discrepancy sits in the ledger like a slow leak nobody can hear.

The reconciliation framework exists to make that impossible. It runs as an independent auditor -- stateless, deterministic, never touching the data it reads -- that matches every payment against its corresponding execution record, flags the gaps, and escalates before a discrepancy can compound.

What it catches:

- **Phantom payments**: money left the wallet, but the service never ran.
- **Unpaid services**: the work was done, but nobody paid for it.
- **Amount drift**: the payment and the invoice don't agree.
- **Velocity spikes and counterparty concentration**: statistical patterns that precede fraud or misconfiguration.
- **Cross-organisation anomalies**: the same bad actor showing up across multiple tenants.

It forwards compliance-relevant findings to jurisdictional authorities and feeds anonymised aggregates into the Sovereign Intelligence layer for network-wide pattern analysis.

---

## 2. Auditor Specification

The reconciliation auditor is a stateless worker that reads from the payments
ledger and the execution records store. It produces a reconciliation report
for each run.

### 2.1 Auditor Identity

| Property        | Value                                    |
|-----------------|------------------------------------------|
| Agent ID        | `agent:reconciliation-auditor-01`        |
| Role            | `system.auditor`                         |
| Permissions     | Read-only on payments, executions, wallets|
| Write Access    | Reconciliation reports, alerts           |

### 2.2 Auditor Guarantees

- **Idempotent**: running the same period twice produces identical results.
- **Deterministic**: no randomness in matching or classification.
- **Non-blocking**: auditor never locks payment or execution tables.
- **Isolated**: runs in a dedicated connection pool with read replicas.

---

## 3. Schedule

### 3.1 Daily Scheduled Run

The primary reconciliation runs daily at 03:00 UTC:

```
0 3 * * *   pulse-reconciliation-worker --mode=scheduled
```

The scheduled run covers the previous 24-hour window:
`[yesterday 03:00 UTC, today 03:00 UTC)`.

### 3.2 On-Demand Trigger

Any authorised operator or system agent may trigger an ad-hoc reconciliation:

```
POST /pulse-api/reconciliation/trigger
Authorization: Bearer {operator_token}
Content-Type: application/json

{
  "start_time": "2026-04-13T00:00:00Z",
  "end_time": "2026-04-13T23:59:59Z",
  "scope": "all",
  "reason": "Investigating anomaly flagged by monitoring"
}
```

Response:

```json
{
  "reconciliation_id": "rec-20260414-adhoc-001",
  "status": "queued",
  "estimated_duration_seconds": 120
}
```

### 3.3 Polling for Results

```
GET /pulse-api/reconciliation/{reconciliation_id}
```

Returns the full report once status transitions to `completed`.

---

## 4. Transaction Matching

### 4.1 Matching Algorithm

For every payment record in the reconciliation window:

```
Step 1  Extract reference_id from the payment record.
Step 2  Look up reference_id in the execution records table.
Step 3  Verify the execution record exists.
Step 4  Verify the execution record status = 'completed'.
Step 5  Verify the execution output hash matches the payment metadata.
Step 6  Classify the match result.
```

### 4.2 Match Outcomes

| Outcome            | Code | Description                                              |
|--------------------|------|----------------------------------------------------------|
| `matched`          | `M`  | Payment maps to a completed execution with matching output.|
| `phantom_payment`  | `PP` | Payment exists but no corresponding execution record found.|
| `unpaid_service`   | `US` | Execution record exists but no corresponding payment found.|

### 4.3 Reference ID Lookup

The `reference_id` is the canonical key linking payments to executions:

```
LOOKUP execution_record
WHERE reference_id = payment_reference_id
  AND org = payment_org
  AND created_at BETWEEN window_start AND window_end
```

If zero rows returned: classify as `phantom_payment`.
If row returned but `status != 'completed'`: classify as `phantom_payment`
(incomplete execution does not satisfy the match).

### 4.4 Reverse Lookup (Unpaid Services)

After forward matching, the auditor performs a reverse scan:

```
LOOKUP execution_records
WHERE org = org_id
  AND created_at BETWEEN window_start AND window_end
  AND reference_id NOT IN (payment reference_ids for same org and window)
  AND status = 'completed'
  AND billable = true
```

Each result is classified as `unpaid_service`.

---

## 5. Amount Consistency Check

For every `matched` pair, the auditor compares the payment amount against the
execution's declared cost:

```
deviation = abs(payment.amount - execution.declared_cost) / execution.declared_cost
```

If `deviation > 0.10` (10% threshold), the match is flagged as
`amount_mismatch` and the severity is set to `medium`.

### 5.1 Threshold Configuration

| Parameter                  | Default | Description                          |
|----------------------------|---------|--------------------------------------|
| `amount_match_threshold`   | 0.10    | Maximum allowed relative deviation   |
| `currency_conversion_grace`| 0.02    | Additional tolerance for cross-currency|

Cross-currency payments receive the combined tolerance:
`threshold = amount_match_threshold + currency_conversion_grace` = 12%.

---

## 6. Multi-Engine Anomaly Detection

The anomaly detection module applies statistical and pattern-based rules
over the reconciliation dataset and the 90-day rolling baseline.

### 6.1 Counterparty Concentration

**Rule**: If a single counterparty accounts for more than 40% of an agent's
total transaction volume (by count or amount) in the reconciliation window,
flag as `counterparty_concentration`.

```
concentration = agent_counterparty_volume / agent_total_volume
if concentration > 0.40:
    flag anomaly(type="counterparty_concentration", severity=medium)
```

### 6.2 Velocity Change

**Rule**: If an agent's transaction velocity (count per hour) exceeds
2 standard deviations above the 30-day moving average, flag as
`velocity_anomaly`.

```
current_velocity = count_in_window / hours_in_window
baseline_ma = 30_day_moving_average(agent_velocity)
baseline_sd = 30_day_stddev(agent_velocity)

if current_velocity > baseline_ma + (2 * baseline_sd):
    flag anomaly(type="velocity_change", severity=high)
```

### 6.3 New Category Detection

**Rule**: If a payment references a category that the agent has never used
in the previous 90 days, flag as `new_category`.

```
known_categories = categories_used_in_last_90_days(agent_id)
if payment.category not in known_categories:
    flag anomaly(type="category_drift", severity=low)
```

### 6.4 Cross-Organisation Patterns

**Rule**: If the same counterparty appears in anomalous transactions across
multiple organisations within the same reconciliation window, flag as
`cross_org_pattern`.

```
for each flagged counterparty:
    orgs_affected = count_distinct_orgs_with_anomalies(counterparty)
    if orgs_affected > 1:
        flag anomaly(type="cross_org_pattern", severity=critical)
```

---

## 7. Severity Classification

Each anomaly or discrepancy is assigned a severity level based on the
following rules, evaluated in priority order:

### 7.1 Critical

An item is `critical` if ANY of the following are true:

- Total discrepancy count > 5 in the reconciliation window.
- Total discrepancy amount > $10,000 USD equivalent.
- Cross-organisation pattern detected.

### 7.2 High

An item is `high` if ANY of the following are true (and not critical):

- Total discrepancy count > 2 in the reconciliation window.
- Total discrepancy amount > $1,000 USD equivalent.
- Velocity anomaly detected.

### 7.3 Medium

An item is `medium` if ANY of the following are true (and not high/critical):

- Amount mismatch detected (>10% deviation).
- Counterparty concentration detected (>40%).

### 7.4 Low

An item is `low` if:

- Category drift detected (new category usage).
- No other higher-severity conditions apply.

### 7.5 Severity Escalation

Severities compound across reconciliation runs. If a `medium` anomaly
persists for 3 consecutive daily runs, it is automatically escalated to `high`.
If a `high` anomaly persists for 5 consecutive runs, it escalates to `critical`.

---

## 8. Report Schema

Each reconciliation run produces a structured report:

```json
{
  "reconciliation_id": "rec-20260414-daily-001",
  "type": "scheduled",
  "window": {
    "start": "2026-04-13T03:00:00Z",
    "end": "2026-04-14T03:00:00Z"
  },
  "summary": {
    "total_payments": 1247,
    "total_executions": 1253,
    "matched": 1240,
    "phantom_payments": 3,
    "unpaid_services": 6,
    "amount_mismatches": 2,
    "anomalies_detected": 4
  },
  "discrepancies": [
    {
      "type": "phantom_payment",
      "payment_id": "pay-90812",
      "reference_id": "ref-xk209",
      "amount": 150.00,
      "currency": "USD",
      "severity": "high",
      "details": "No execution record found for reference_id."
    }
  ],
  "anomalies": [
    {
      "type": "velocity_change",
      "agent_id": "agent:data-processor-05",
      "severity": "high",
      "current_value": 42.5,
      "baseline_mean": 18.3,
      "baseline_stddev": 6.1,
      "threshold": 30.5,
      "details": "Transaction velocity 2.3x above 30-day moving average."
    },
    {
      "type": "counterparty_concentration",
      "agent_id": "agent:payment-router-02",
      "counterparty": "agent:vendor-api-11",
      "severity": "medium",
      "concentration_pct": 47.2,
      "threshold_pct": 40.0,
      "details": "Single counterparty represents 47.2% of volume."
    }
  ],
  "metadata": {
    "auditor_version": "2.4.0",
    "duration_seconds": 87,
    "records_scanned": 2500,
    "baseline_days": 90
  }
}
```

---

## 9. Alert Routing via Dispatcher

The Dispatcher receives reconciliation alerts and routes them based on
severity and type.

### 9.1 Routing Rules

| Severity | Channel               | Response SLA | Auto-Action            |
|----------|-----------------------|--------------|------------------------|
| Critical | Ops team + exec alert | 1 hour       | Freeze affected agents |
| High     | Ops team notification | 4 hours      | Flag for review        |
| Medium   | Daily digest          | 24 hours     | Include in report      |
| Low      | Weekly summary        | 7 days       | Log only               |

### 9.2 Dispatcher Payload

```json
{
  "alert_id": "alert-rec-20260414-001",
  "source": "reconciliation-auditor",
  "severity": "critical",
  "reconciliation_id": "rec-20260414-daily-001",
  "summary": "3 phantom payments totalling $4,500 detected across org:acme-corp",
  "action_required": "Investigate and resolve within SLA.",
  "routing": {
    "channels": ["ops-team", "exec-alerts"],
    "escalation_chain": ["ops-lead", "finance-director"]
  }
}
```

### 9.3 Alert Lifecycle

```
Created -> Acknowledged -> Investigating -> Resolved
```

Unacknowledged alerts escalate after 50% of the SLA window has elapsed.

---

## 10. Compliance Data Forwarding

For organisations operating in regulated jurisdictions, the reconciliation
framework forwards relevant data to compliance systems.

### 10.1 Forwarding Trigger

Compliance forwarding is triggered when:

- A discrepancy involves an amount above the jurisdictional reporting threshold.
- The transaction involves a counterparty flagged in sanctions lists.
- Cross-organisation anomalies are detected.

### 10.2 Forwarding Endpoint

```
POST /pulse-api/compliance/reports
Body: {
  "reconciliation_id": "rec-20260414-daily-001",
  "jurisdiction": "US",
  "report_type": "suspicious_activity",
  "items": [ ... filtered discrepancies and anomalies ... ],
  "generated_at": "2026-04-14T03:02:15Z"
}
```

### 10.3 Supported Jurisdictions

| Code   | Jurisdiction                | Reporting Threshold |
|--------|-----------------------------|---------------------|
| `US`   | United States               | $3,000 USD          |
| `EU`   | European Union              | 2,500 EUR           |
| `UAE`  | United Arab Emirates        | 10,000 AED          |
| `LATAM`| Latin America (aggregate)   | $5,000 USD          |

---

## 11. Sovereign Intelligence Ingestion

Anonymised reconciliation data is forwarded to the Sovereign Intelligence
layer for network-wide pattern analysis.

### 11.1 Anonymisation Rules

- All agent IDs are replaced with salted hashes (rotated monthly).
- Organisation names are stripped; only `org_sector` is retained.
- Transaction amounts are bucketed into ranges (0-100, 100-1K, 1K-10K, 10K+).
- Timestamps are truncated to hourly granularity.
- No personally identifiable information is included.

### 11.2 Ingestion Payload

```json
{
  "source": "reconciliation",
  "period": "2026-04-13/2026-04-14",
  "metrics": {
    "match_rate": 0.994,
    "phantom_rate": 0.002,
    "unpaid_rate": 0.004,
    "anomaly_count": 4,
    "severity_distribution": {
      "critical": 0,
      "high": 2,
      "medium": 1,
      "low": 1
    }
  },
  "patterns": [
    {
      "type": "velocity_trend",
      "direction": "increasing",
      "sector": "logistics",
      "magnitude": 1.8
    }
  ]
}
```

### 11.3 Ingestion Endpoint

```
POST /pulse-api/sovereign/ingest
Authorization: Bearer {system_service_token}
```

Only system-level service tokens with the `sovereign.write` scope may
submit data to this endpoint.

---

## 12. 90-Day Rolling Baseline

All anomaly detection rules reference a rolling 90-day baseline computed
from historical reconciliation data.

### 12.1 Baseline Metrics

| Metric                      | Computation                                   |
|-----------------------------|-----------------------------------------------|
| `agent_velocity_ma`         | 30-day moving average of hourly tx count       |
| `agent_velocity_sd`         | 30-day standard deviation of hourly tx count   |
| `counterparty_distribution` | 90-day volume share per counterparty per agent |
| `category_set`              | Distinct categories used in last 90 days       |
| `amount_distribution`       | 90-day percentile buckets per agent            |

### 12.2 Baseline Refresh

The baseline is recomputed daily as part of the scheduled reconciliation
run. The computation runs after the reconciliation report is generated
so that the current day's data is included in the next baseline.

### 12.3 Cold Start

For agents with less than 30 days of history, the system uses
organisation-wide averages as the baseline. For agents with less than
7 days, anomaly detection is disabled and all transactions are flagged
for manual review.

### 12.4 Baseline Storage

Baselines are stored in a dedicated time-series store keyed by agent, organization, metric name, and computation timestamp. Each record includes the metric value and the window size (default: 90 days). Baselines older than 180 days are archived to cold storage.

---

## 13. API Reference

| Method | Endpoint                                | Description                        |
|--------|-----------------------------------------|------------------------------------|
| POST   | `/pulse-api/reconciliation/trigger`     | Trigger ad-hoc reconciliation      |
| GET    | `/pulse-api/reconciliation/{id}`        | Get reconciliation report          |
| GET    | `/pulse-api/reconciliation/latest`      | Get most recent report             |
| GET    | `/pulse-api/reconciliation/history`     | List past reconciliation runs      |
| POST   | `/pulse-api/compliance/reports`         | Forward compliance data            |
| POST   | `/pulse-api/sovereign/ingest`           | Submit anonymised data             |
| GET    | `/pulse-api/reconciliation/baselines`   | Query current baseline metrics     |

---

*End of Reconciliation Framework specification.*

# Spending Policy Schema

> A2A Payment Protocol -- Agent Spending Controls, Inheritance & Enforcement

---

## 1. Overview

Spending policies define the financial boundaries within which Pulse Engines
operate. Every payment authorisation is evaluated against the active policy
before funds are committed. Policies are composable, inheritable across
multi-tenant hierarchies, and snapshotted at authorisation time to ensure
deterministic audit trails.

---

## 2. Policy Parameters

### 2.1 `max_per_transaction`

| Property    | Value                                                      |
|-------------|------------------------------------------------------------|
| Type        | `number` (decimal, 2 decimal places)                       |
| Default     | `null` (no per-transaction limit)                          |
| Unit        | Base currency of the agent's wallet                        |
| Validation  | Must be > 0 if set. Must not exceed `max_daily`.           |

**Behaviour**: If a single payment request exceeds this value, the
authorisation pipeline rejects the request at step 4 (policy evaluation)
with error code `POLICY_MAX_TXN_EXCEEDED`.

```json
{
  "max_per_transaction": 500.00
}
```

### 2.2 `max_daily`

| Property    | Value                                                      |
|-------------|------------------------------------------------------------|
| Type        | `number` (decimal, 2 decimal places)                       |
| Default     | `null` (no daily limit)                                    |
| Unit        | Base currency of the agent's wallet                        |
| Validation  | Must be > 0 if set. Must be >= `max_per_transaction`.      |

**Behaviour**: Computed as a **rolling 24-hour SUM** of all settled and
pending payments for the agent. The window is `[NOW - 24h, NOW]`.

```sql
SELECT COALESCE(SUM(amount), 0)
FROM payments
WHERE agent_id = :agent_id
  AND status IN ('settled', 'pending', 'held')
  AND created_at >= NOW() - INTERVAL '24 hours'
```

If `current_daily_total + requested_amount > max_daily`, the request is
rejected with `POLICY_MAX_DAILY_EXCEEDED`.

### 2.3 `max_monthly`

| Property    | Value                                                      |
|-------------|------------------------------------------------------------|
| Type        | `number` (decimal, 2 decimal places)                       |
| Default     | `null` (no monthly limit)                                  |
| Unit        | Base currency of the agent's wallet                        |
| Validation  | Must be > 0 if set. Must be >= `max_daily`.                |

**Behaviour**: Computed as a **rolling 30-day SUM**. The window is
`[NOW - 30d, NOW]`.

```sql
SELECT COALESCE(SUM(amount), 0)
FROM payments
WHERE agent_id = :agent_id
  AND status IN ('settled', 'pending', 'held')
  AND created_at >= NOW() - INTERVAL '30 days'
```

Rejection code: `POLICY_MAX_MONTHLY_EXCEEDED`.

### 2.4 `approved_counterparties`

| Property    | Value                                                      |
|-------------|------------------------------------------------------------|
| Type        | `array<string>` (agent URIs or org IDs)                    |
| Default     | `[]` (empty = unrestricted)                                |
| Validation  | Each entry must be a valid agent URI or org ID.            |

**Behaviour**: When the array is **empty**, the agent may transact with
any counterparty not on the blocked list. When **non-empty**, only
counterparties listed here are permitted.

```json
{
  "approved_counterparties": [
    "agent:vendor-api-11",
    "agent:logistics-engine-07",
    "org:trusted-partners"
  ]
}
```

Rejection code: `POLICY_COUNTERPARTY_NOT_APPROVED`.

### 2.5 `blocked_counterparties`

| Property    | Value                                                      |
|-------------|------------------------------------------------------------|
| Type        | `array<string>` (agent URIs or org IDs)                    |
| Default     | `[]` (no blocks)                                           |
| Validation  | Each entry must be a valid agent URI or org ID.            |

**Behaviour**: Checked **before** the approved list. A counterparty on the
blocked list is rejected regardless of whether it also appears on the
approved list. The blocked list has **absolute precedence**.

Evaluation order:

```
1. Is counterparty in blocked_counterparties?
   YES -> reject with POLICY_COUNTERPARTY_BLOCKED
2. Is approved_counterparties non-empty?
   YES -> Is counterparty in approved_counterparties?
          NO  -> reject with POLICY_COUNTERPARTY_NOT_APPROVED
          YES -> proceed
   NO  -> proceed (unrestricted)
```

### 2.6 `allowed_categories`

| Property    | Value                                                      |
|-------------|------------------------------------------------------------|
| Type        | `array<string>` (category codes)                           |
| Default     | `[]` (empty = all categories allowed)                      |
| Validation  | Each entry must match a registered category code.          |

**Behaviour**: When non-empty, only payments tagged with a listed category
are permitted. Category codes follow a hierarchical dot notation:
`compute.gpu`, `data.storage`, `logistics.shipping`.

```json
{
  "allowed_categories": [
    "compute.gpu",
    "compute.cpu",
    "data.storage"
  ]
}
```

A payment tagged `data.transfer` would be rejected with
`POLICY_CATEGORY_NOT_ALLOWED`.

### 2.7 `require_human_above`

| Property    | Value                                                      |
|-------------|------------------------------------------------------------|
| Type        | `number | null` (decimal, 2 decimal places)                |
| Default     | `null` (no human approval required)                        |
| Validation  | Must be > 0 if set.                                        |

**Behaviour**: When set, any payment with `amount >= require_human_above`
triggers an **escalation** to a human operator for manual approval. The
payment enters `pending_approval` state and does not proceed until the
operator approves or rejects it.

```json
{
  "require_human_above": 1000.00
}
```

Escalation flow:

```
Step 1  Auth pipeline detects amount >= require_human_above.
Step 2  Payment state set to pending_approval.
Step 3  Dispatcher sends approval request to designated operator.
Step 4  Operator approves -> payment proceeds through remaining pipeline.
        Operator rejects -> payment rejected with POLICY_HUMAN_REJECTED.
Step 5  Approval SLA: 4 hours. If no response, auto-reject.
```

### 2.8 `compliance_precheck` and `compliance_jurisdictions`

| Property                   | Value                                          |
|----------------------------|------------------------------------------------|
| `compliance_precheck` Type | `boolean`                                      |
| `compliance_precheck` Default | `false`                                     |
| `compliance_jurisdictions` Type | `array<string>` (jurisdiction codes)       |
| `compliance_jurisdictions` Default | `[]`                                    |
| Validation                 | Jurisdictions must be in: US, EU, UAE, LATAM   |

**Behaviour**: When `compliance_precheck` is `true`, every payment is
screened against the compliance rules for the specified jurisdictions
before authorisation completes.

```json
{
  "compliance_precheck": true,
  "compliance_jurisdictions": ["US", "EU"]
}
```

The compliance check includes:

- Sanctions list screening for the counterparty.
- Transaction amount threshold checks per jurisdiction.
- Category restrictions per jurisdiction.
- Reporting obligations triggered (logged for downstream forwarding).

If any jurisdiction check fails, the payment is rejected with
`POLICY_COMPLIANCE_FAILED` and the failure details are logged.

---

## 3. Policy Resolution Priority

When multiple policy sources apply, they are resolved in the following
priority order (highest first):

```
Priority 1: Agent-specific policy override
Priority 2: Organisation-wide default policy
Priority 3: Fund-level policy (in multi-tenancy)
Priority 4: System-wide defaults
```

### 3.1 Merge Strategy

Policies are **not merged**. The highest-priority policy that defines a
parameter wins for that parameter. If an agent-specific policy defines
`max_per_transaction` but not `max_daily`, the system looks to the
org-wide policy for `max_daily`, and so on down the chain.

```python
def resolve_parameter(param_name, agent_policy, org_policy, fund_policy, system_defaults):
    for policy in [agent_policy, org_policy, fund_policy, system_defaults]:
        if policy is not None and param_name in policy and policy[param_name] is not None:
            return policy[param_name]
    return None  # No limit set at any level
```

### 3.2 Override Restrictions

A lower-priority policy cannot **relax** a limit set by a higher-priority
parent. The enforcement is:

- Child `max_per_transaction` must be <= parent `max_per_transaction`.
- Child `max_daily` must be <= parent `max_daily`.
- Child `max_monthly` must be <= parent `max_monthly`.
- Child `blocked_counterparties` must be a superset of parent's blocked list.
- Child `require_human_above` must be <= parent `require_human_above` (if set).

Attempts to save a policy that violates these constraints return
HTTP 422 with error code `POLICY_INHERITANCE_VIOLATION`.

---

## 4. Organisation-Wide vs Agent-Specific Policies

### 4.1 Organisation-Wide Policy

Set via:

```
PUT /pulse-api/orgs/{org_id}/spending-policy
```

Applies to all agents in the organisation unless overridden.

### 4.2 Agent-Specific Policy

Set via:

```
PUT /pulse-api/agents/{agent_id}/spending-policy
```

Overrides the org-wide policy for this specific agent. Only parameters
explicitly set in the agent policy take effect; unset parameters fall
through to the org-wide policy.

---

## 5. Inheritance in Multi-Tenancy

In a fund-of-funds or parent-child organisational structure, policies
cascade through the hierarchy:

```
Fund (top-level entity)
  |
  +-- Child Org A
  |     +-- Agent A1
  |     +-- Agent A2
  |
  +-- Child Org B
        +-- Agent B1
```

### 5.1 Fund-Level Policy

Set via:

```
PUT /pulse-api/funds/{fund_id}/spending-policy
```

This is the ceiling. No child organisation or agent can exceed the
fund-level limits.

### 5.2 Cascade Example

```
Fund policy:        max_daily = 50,000
Child Org A policy: max_daily = 20,000   (valid: 20,000 <= 50,000)
Agent A1 policy:    max_daily = 5,000    (valid: 5,000 <= 20,000)
Agent A2 policy:    max_daily = null     (inherits 20,000 from org)
```

If Agent A1 tries to set `max_daily = 25,000`, the API rejects with
`POLICY_INHERITANCE_VIOLATION` because 25,000 > 20,000 (org limit).

### 5.3 Blocked Counterparty Propagation

Blocked counterparties propagate downward and accumulate:

```
Fund blocks:     [agent:sanctioned-01]
Child Org blocks:[agent:untrusted-vendor-05]
Agent blocks:    [agent:competitor-07]

Effective blocked list for Agent:
  [agent:sanctioned-01, agent:untrusted-vendor-05, agent:competitor-07]
```

The effective blocked list is the **union** of all ancestor blocked lists
plus the agent's own blocked list. Removal of an entry at a child level
does not override a parent's block.

---

## 6. Policy Snapshot Mechanism

When a payment is authorised, the **effective policy at the moment of
authorisation** is frozen and stored as a snapshot in the authorisation
record. This ensures:

- Subsequent policy changes do not retroactively affect in-flight payments.
- Auditors can verify which policy was active when the payment was approved.
- Dispute resolution references the exact policy that applied.

### 6.1 Snapshot Schema

```json
{
  "auth_id": "auth-20260414-001",
  "agent_id": "agent:data-processor-05",
  "policy_snapshot": {
    "max_per_transaction": 500.00,
    "max_daily": 5000.00,
    "max_monthly": 50000.00,
    "approved_counterparties": [],
    "blocked_counterparties": ["agent:sanctioned-01"],
    "allowed_categories": ["compute.gpu", "compute.cpu"],
    "require_human_above": 1000.00,
    "compliance_precheck": true,
    "compliance_jurisdictions": ["US", "EU"],
    "resolved_from": {
      "max_per_transaction": "agent",
      "max_daily": "agent",
      "max_monthly": "org",
      "approved_counterparties": "system_default",
      "blocked_counterparties": "merged",
      "allowed_categories": "agent",
      "require_human_above": "org",
      "compliance_precheck": "org",
      "compliance_jurisdictions": "org"
    }
  },
  "snapshot_at": "2026-04-14T10:30:00Z"
}
```

The `resolved_from` map records which level provided each parameter value,
enabling full traceability.

### 6.2 Snapshot Storage

Snapshots are stored in the `auth_policy_snapshots` table and are
immutable. They are retained for the same duration as the associated
payment record (minimum 7 years for compliance).

---

## 7. Active/Inactive Toggle

Policies can be toggled between active and inactive states:

```
PATCH /pulse-api/agents/{agent_id}/spending-policy
Body: { "active": false }
```

### 7.1 Inactive Policy Behaviour

When a policy is set to `inactive`:

- The agent falls back to the next level in the inheritance chain.
- If no parent policy exists, system defaults apply.
- The inactive policy is retained and can be reactivated at any time.
- Deactivation is logged in the audit trail.

### 7.2 Emergency Deactivation

An admin can deactivate all agent-level policies in an organisation:

```
POST /pulse-api/orgs/{org_id}/spending-policy/emergency-reset
Body: { "reason": "Suspected compromise", "admin_id": "admin:ops-lead-01" }
```

This sets all agent-level policies to `inactive` and forces the org-wide
policy to apply uniformly. It emits a `policy.emergency_reset` event.

---

## 8. Detailed Examples

### 8.1 Restrictive Policy

A compliance-heavy agent that handles regulated payments:

```json
{
  "agent_id": "agent:compliance-processor-01",
  "policy": {
    "active": true,
    "max_per_transaction": 250.00,
    "max_daily": 2000.00,
    "max_monthly": 15000.00,
    "approved_counterparties": [
      "agent:verified-vendor-01",
      "agent:verified-vendor-02",
      "agent:verified-vendor-03"
    ],
    "blocked_counterparties": [
      "agent:sanctioned-01",
      "agent:high-risk-vendor-09"
    ],
    "allowed_categories": [
      "compliance.screening",
      "compliance.reporting"
    ],
    "require_human_above": 100.00,
    "compliance_precheck": true,
    "compliance_jurisdictions": ["US", "EU", "UAE"]
  }
}
```

**Effect**: This agent can only transact with 3 specific vendors, only
for compliance-related categories, with human approval required for
anything over $100, and full compliance screening in 3 jurisdictions.

### 8.2 Permissive Policy

A general-purpose utility agent with broad autonomy:

```json
{
  "agent_id": "agent:utility-router-07",
  "policy": {
    "active": true,
    "max_per_transaction": 5000.00,
    "max_daily": 25000.00,
    "max_monthly": 200000.00,
    "approved_counterparties": [],
    "blocked_counterparties": [
      "agent:sanctioned-01"
    ],
    "allowed_categories": [],
    "require_human_above": null,
    "compliance_precheck": false,
    "compliance_jurisdictions": []
  }
}
```

**Effect**: This agent can transact with anyone except the sanctioned
entity, in any category, up to $5K per transaction with no human
approval required. Compliance pre-checks are disabled (the org may
handle compliance at a different layer).

### 8.3 Fund Cascade

A fund with two child organisations demonstrating inheritance:

```json
{
  "fund_id": "fund:growth-capital-01",
  "fund_policy": {
    "active": true,
    "max_per_transaction": 10000.00,
    "max_daily": 100000.00,
    "max_monthly": 1000000.00,
    "approved_counterparties": [],
    "blocked_counterparties": [
      "agent:sanctioned-01",
      "agent:sanctioned-02"
    ],
    "allowed_categories": [],
    "require_human_above": 5000.00,
    "compliance_precheck": true,
    "compliance_jurisdictions": ["US", "EU"]
  },
  "child_orgs": [
    {
      "org_id": "org:portfolio-alpha",
      "org_policy": {
        "active": true,
        "max_per_transaction": 5000.00,
        "max_daily": 50000.00,
        "max_monthly": null,
        "blocked_counterparties": [
          "agent:untrusted-vendor-05"
        ],
        "require_human_above": 2000.00
      },
      "agents": [
        {
          "agent_id": "agent:alpha-trader-01",
          "agent_policy": {
            "active": true,
            "max_per_transaction": 1000.00,
            "max_daily": 10000.00
          }
        },
        {
          "agent_id": "agent:alpha-analyst-02",
          "agent_policy": {
            "active": false
          }
        }
      ]
    },
    {
      "org_id": "org:portfolio-beta",
      "org_policy": {
        "active": true,
        "max_per_transaction": 8000.00,
        "max_daily": 80000.00,
        "max_monthly": 500000.00,
        "require_human_above": 3000.00
      }
    }
  ]
}
```

**Effective policies**:

| Agent                  | max_per_txn | max_daily | max_monthly | human_above | blocked (effective)                                      |
|------------------------|-------------|-----------|-------------|-------------|----------------------------------------------------------|
| agent:alpha-trader-01  | 1,000       | 10,000    | 1,000,000*  | 2,000**     | sanctioned-01, sanctioned-02, untrusted-vendor-05        |
| agent:alpha-analyst-02 | 5,000***    | 50,000*** | 1,000,000*  | 2,000**     | sanctioned-01, sanctioned-02, untrusted-vendor-05        |
| org:portfolio-beta agents | 8,000    | 80,000    | 500,000     | 3,000       | sanctioned-01, sanctioned-02                             |

`*` Inherited from fund (org did not set max_monthly).
`**` Inherited from org (agent did not set require_human_above).
`***` Inherited from org (agent policy is inactive).

---

## 9. API Reference

| Method | Endpoint                                         | Description                       |
|--------|--------------------------------------------------|-----------------------------------|
| GET    | `/pulse-api/agents/{id}/spending-policy`         | Get agent effective policy        |
| PUT    | `/pulse-api/agents/{id}/spending-policy`         | Set agent-specific policy         |
| PATCH  | `/pulse-api/agents/{id}/spending-policy`         | Partial update agent policy       |
| GET    | `/pulse-api/orgs/{id}/spending-policy`           | Get org-wide policy               |
| PUT    | `/pulse-api/orgs/{id}/spending-policy`           | Set org-wide policy               |
| POST   | `/pulse-api/orgs/{id}/spending-policy/emergency-reset` | Emergency reset all agent policies |
| GET    | `/pulse-api/funds/{id}/spending-policy`          | Get fund-level policy             |
| PUT    | `/pulse-api/funds/{id}/spending-policy`          | Set fund-level policy             |
| GET    | `/pulse-api/auth/{id}/policy-snapshot`           | Get policy snapshot for auth record|

---

## 10. Error Codes

| Code                            | HTTP | Description                                    |
|---------------------------------|------|------------------------------------------------|
| `POLICY_MAX_TXN_EXCEEDED`      | 403  | Amount exceeds max_per_transaction             |
| `POLICY_MAX_DAILY_EXCEEDED`    | 403  | Rolling 24h total would exceed max_daily       |
| `POLICY_MAX_MONTHLY_EXCEEDED`  | 403  | Rolling 30d total would exceed max_monthly     |
| `POLICY_COUNTERPARTY_BLOCKED`  | 403  | Counterparty is on the blocked list            |
| `POLICY_COUNTERPARTY_NOT_APPROVED` | 403 | Counterparty not in approved list            |
| `POLICY_CATEGORY_NOT_ALLOWED`  | 403  | Payment category not in allowed list           |
| `POLICY_HUMAN_REJECTED`        | 403  | Human operator rejected the payment            |
| `POLICY_COMPLIANCE_FAILED`     | 403  | Compliance pre-check failed                    |
| `POLICY_INHERITANCE_VIOLATION` | 422  | Child policy exceeds parent constraints        |

---

## 11. Common Mistakes

These three misconfigurations account for the majority of support escalations. All of them pass schema validation -- the policy saves successfully -- and then cause problems at runtime.

### 11.1 Setting `max_daily` lower than `max_per_transaction`

```json
{
  "max_per_transaction": 5000.00,
  "max_daily": 2000.00
}
```

Every transaction above $2,000 gets denied with `POLICY_MAX_DAILY_EXCEEDED` on the first attempt of the day -- even though `max_per_transaction` nominally allows up to $5,000. The daily rolling sum check runs *before* the per-transaction check, so the higher per-transaction limit never gets a chance to matter. The fix: `max_daily` must always be >= `max_per_transaction`. The API warns on save but does not reject, because some operators intentionally set this for agents that should only make a single large payment per day.

### 11.2 Forgetting to set `require_human_above`

```json
{
  "max_per_transaction": 10000.00,
  "max_daily": 50000.00,
  "require_human_above": null
}
```

This agent can spend $50,000 per day with zero human oversight. If that's intentional, fine. But in practice this is the most common "I didn't realize" configuration: the operator sets generous limits assuming a human will review large transactions, then discovers weeks later that every payment sailed through automatically. **If you want a human in the loop, you must explicitly set `require_human_above` to a dollar amount.** The system does not infer oversight requirements from limit sizes.

### 11.3 Enabling `compliance_precheck` without setting `compliance_jurisdictions`

```json
{
  "compliance_precheck": true,
  "compliance_jurisdictions": []
}
```

The compliance precheck flag is `true`, so the authorization pipeline dutifully runs the compliance screening step on every payment. But with an empty jurisdictions array, the screening has no rules to evaluate against -- it checks nothing, finds nothing, and returns `passed` every time. The operator believes compliance is active. It is not. **Always pair `compliance_precheck: true` with at least one jurisdiction** (e.g., `["US"]`). The system logs a warning on save but does not block the configuration.

---

*End of Spending Policy Schema specification.*

# Multi-Tenancy Payments

Version: 4.17.0 | Protocol: A2A Payment Protocol | Engine: Pulse Engines

---

## Overview

The Pulse Engines payment system supports a hierarchical multi-tenant architecture
designed for PE fund structures, holding companies, and any parent-child organizational
model. Each organization maintains strict data isolation while enabling controlled
cross-organization transactions between autonomous agents. This document covers the
org hierarchy, database isolation model, policy cascade and resolution, cross-org
transaction handling, roll-up reporting, wallet isolation, and scale characteristics.

---

## Parent-Child Organization Hierarchy

### Structure

Organizations are arranged in a tree structure with no depth limit:

```
PE Fund (Level 0 - Root)
  |
  +-- Portco A (Level 1)
  |     |
  |     +-- Portco A - Division East (Level 2)
  |     +-- Portco A - Division West (Level 2)
  |           |
  |           +-- Portco A - West - Branch 1 (Level 3)
  |           +-- Portco A - West - Branch 2 (Level 3)
  |
  +-- Portco B (Level 1)
  |     |
  |     +-- Portco B - OpCo 1 (Level 2)
  |     +-- Portco B - OpCo 2 (Level 2)
  |
  +-- Portco C (Level 1)
  ...
  +-- Portco N (Level 1)
```

### Organization Record

Each organization record contains:

```json
{
  "id": "org_abc123",
  "name": "Portco A - Division West",
  "slug": "portco-a-west",
  "type": "subsidiary",
  "parent_org_id": "org_portco_a",
  "root_org_id": "org_pe_fund",
  "hierarchy_path": ["org_pe_fund", "org_portco_a", "org_portco_a_west"],
  "hierarchy_depth": 2,
  "status": "active",
  "subscription_tier": "enterprise",
  "settings": {
    "default_currency": "USD",
    "timezone": "America/New_York",
    "compliance_jurisdictions": ["US_FEDERAL", "US_STATE_NY"]
  },
  "created_at": "2026-01-15T00:00:00.000Z"
}
```

### N-Level Depth Support

The hierarchy supports unlimited nesting depth. The `hierarchy_path` array stores
the full ancestry chain from the root organization to the current node. This enables
efficient ancestor and descendant queries without recursive joins:

- **Find all ancestors**: Read `hierarchy_path` directly.
- **Find all descendants**: Query where `hierarchy_path` contains the target org ID.
- **Find siblings**: Query where `parent_org_id` matches.
- **Find depth**: Read `hierarchy_depth` or count `hierarchy_path` elements.

### Organization Types

| Type           | Description                                              |
| -------------- | -------------------------------------------------------- |
| `fund`         | Top-level PE fund or holding company (root node)         |
| `portfolio`    | Direct portfolio company owned by the fund               |
| `subsidiary`   | Subsidiary of a portfolio company                        |
| `division`     | Operational division within a subsidiary                 |
| `branch`       | Branch office or unit within a division                  |

---

## Database-Level Row Isolation

Every payment-related table enforces row-level isolation using the `org_id` column
and database-level Row Level Security (RLS) policies.

### Isolation Boundaries

| Resource                       | Isolation Column | RLS Policy                    |
| ------------------------------ | ---------------- | ----------------------------- |
| Transactions                   | `org_id`         | org_id = auth.org_id          |
| Authorizations                 | `org_id`         | org_id = auth.org_id          |
| Events                         | `org_id`         | org_id = auth.org_id          |
| Wallets                        | `org_id`         | org_id = auth.org_id          |
| Escrows                        | `org_id`         | org_id = auth.org_id          |
| Spending Policies              | `org_id`         | org_id = auth.org_id          |
| Reports                        | `org_id`         | org_id = auth.org_id          |
| Webhook Endpoints              | `org_id`         | org_id = auth.org_id          |
| Deliveries                     | `org_id`         | org_id = auth.org_id          |

### RLS Policy Definition

The platform enforces organization isolation at the database level using row-level security policies. Each resource is restricted so that only requests authenticated for a given organization can access that organization's data. Administrative operations use elevated privileges that bypass row-level policies, ensuring system integrity while maintaining tenant boundaries.

### Isolation Guarantees

1. **No cross-org data leakage**: An API key authenticated for Org A can never
   read, modify, or reference data belonging to Org B.
2. **Service role controlled**: Cross-org operations (settlement between orgs)
   use the service role with explicit org_id parameters, never implicit auth.
3. **Index-backed filtering**: The `org_id` column is the leading column in all
   composite indexes, ensuring isolation checks are index-only operations.
4. **Audit trail per org**: Every query against payment tables includes the org_id
   filter in the query plan, visible in query logs for audit purposes.

---

## Policy Cascade

Spending policies follow a three-tier cascade from fund-level defaults down to
agent-specific overrides.

### Policy Tiers

```
Tier 1: Fund Default Policy
    (applies to all child orgs unless overridden)
        |
        v
Tier 2: Child Org Default Policy
    (applies to all agents in this org unless overridden)
        |
        v
Tier 3: Agent-Specific Policy
    (applies to a single agent, overrides all defaults)
```

### Fund Default Policy

Created at the root organization level with `agent_id` set to `null`. This policy
applies to every agent in every descendant organization unless a more specific
policy exists.

```json
{
  "id": "pol_fund_default",
  "org_id": "org_pe_fund",
  "policy_name": "Fund-Wide Default",
  "agent_id": null,
  "max_per_transaction": 10000.00,
  "max_daily": 50000.00,
  "max_monthly": 500000.00,
  "currency": "USD",
  "require_human_above": 25000.00,
  "approved_counterparties": [],
  "blocked_counterparties": [],
  "allowed_categories": [],
  "compliance_precheck": true,
  "compliance_jurisdictions": ["US_FEDERAL"],
  "is_active": true
}
```

### Child Org Default Policy

Created at any descendant organization level with `agent_id` set to `null`. Overrides
the fund default for all agents within that specific org.

```json
{
  "id": "pol_portco_a_default",
  "org_id": "org_portco_a",
  "policy_name": "Portco A Default",
  "agent_id": null,
  "max_per_transaction": 5000.00,
  "max_daily": 25000.00,
  "max_monthly": 250000.00,
  "currency": "USD",
  "require_human_above": 10000.00,
  "approved_counterparties": [],
  "blocked_counterparties": ["agent-blocked-vendor"],
  "allowed_categories": ["operations", "procurement"],
  "compliance_precheck": true,
  "compliance_jurisdictions": ["US_FEDERAL", "US_STATE_NY"],
  "is_active": true
}
```

### Agent-Specific Policy

Created with a specific `agent_id`. Overrides all default policies for that agent.

```json
{
  "id": "pol_treasury_ops",
  "org_id": "org_portco_a",
  "policy_name": "Treasury Operations Agent",
  "agent_id": "agent-treasury-ops",
  "max_per_transaction": 50000.00,
  "max_daily": 200000.00,
  "max_monthly": 2000000.00,
  "currency": "USD",
  "require_human_above": 100000.00,
  "approved_counterparties": ["agent-vendor-pay", "agent-payroll"],
  "blocked_counterparties": [],
  "allowed_categories": ["treasury", "operations", "payroll"],
  "compliance_precheck": true,
  "compliance_jurisdictions": ["US_FEDERAL", "US_STATE_NY", "EU_GDPR"],
  "is_active": true
}
```

### Resolution Order

When the authorization pipeline loads the spending policy for a transaction, it
follows this resolution order:

```
1. Look for active policy where org_id = requesting_org AND agent_id = requesting_agent
   -> If found, use this policy. STOP.

2. Look for active policy where org_id = requesting_org AND agent_id IS NULL
   -> If found, use this policy. STOP.

3. Walk up the hierarchy_path from the requesting org to the root:
   For each ancestor org (nearest first):
     a. Look for active policy where org_id = ancestor AND agent_id IS NULL
        -> If found, use this policy. STOP.

4. If no policy found at any level:
   -> DENY the transaction with reason_code "no_applicable_policy"
```

### Policy Field Inheritance

Policy resolution is all-or-nothing. The system does not merge fields from multiple
policy tiers. When a Tier 2 policy is found, it completely replaces the Tier 1
policy -- there is no selective field inheritance. This prevents ambiguity in which
limits apply.

If selective overrides are needed, the child org policy must explicitly set all
fields, including any values carried forward from the parent.

---

## Cross-Organization Transactions

When an agent in Org A sends a payment to an agent in Org B, both organizations'
policies are evaluated independently.

### Dual-Policy Evaluation

```
Agent A (Org A) ──payment──> Agent B (Org B)

Step 1: Load Org A's applicable policy for Agent A
Step 2: Evaluate all Org A policy checks (limits, counterparties, categories)
Step 3: Load Org B's applicable policy for Agent B
Step 4: Evaluate all Org B policy checks (inbound limits, approved senders)
Step 5: BOTH must approve for the transaction to proceed
```

### Both-Must-Approve Rule

The transaction is only authorized if both the sending org's policy AND the
receiving org's policy approve. If either denies, the entire transaction is denied.

| Org A Decision | Org B Decision | Transaction Result |
| -------------- | -------------- | ------------------ |
| Approved       | Approved       | Authorized         |
| Approved       | Denied         | Denied             |
| Denied         | Approved       | Denied             |
| Denied         | Denied         | Denied             |

### Cross-Org Authorization Record

Cross-org transactions produce two authorization records, one per org:

```json
{
  "authorization_id": "auth_org_a_side",
  "transaction_id": "txn_cross_org_1",
  "org_id": "org_a",
  "decision": "approved",
  "side": "sender",
  "policy_id": "pol_org_a_default",
  "reason_code": "policy_pass"
}
```

```json
{
  "authorization_id": "auth_org_b_side",
  "transaction_id": "txn_cross_org_1",
  "org_id": "org_b",
  "decision": "approved",
  "side": "receiver",
  "policy_id": "pol_org_b_default",
  "reason_code": "policy_pass"
}
```

### Cross-Org Compliance

Both organizations' compliance jurisdictions are evaluated. The union of all
jurisdictions from both policies forms the compliance precheck scope:

- Org A policy jurisdictions: `["US_FEDERAL", "US_STATE_NY"]`
- Org B policy jurisdictions: `["US_FEDERAL", "EU_GDPR", "EU_PSD2"]`
- Compliance precheck scope: `["US_FEDERAL", "US_STATE_NY", "EU_GDPR", "EU_PSD2"]`

---

## Roll-Up Reporting

### Fund Administrator View

Fund-level administrators (root org) see aggregate metrics across all descendant
organizations. Individual transaction details are not visible at the fund level.

**Available at fund level:**

- Total transaction volume per portco (sum of amounts)
- Transaction count per portco
- Approval/denial ratio per portco
- Compliance flag count per portco
- Average settlement time per portco
- Wallet balance totals per portco (sum of all agent wallets)

**Not available at fund level:**

- Individual transaction records
- Specific agent wallet balances
- Transaction metadata or descriptions
- Counterparty details
- Authorization decision details

### Roll-Up Query Example

```
GET /pulse-api/reports/financial
Authorization: Bearer YOUR_API_KEY

Response:
{
  "roll_up": {
    "period": "2026-04",
    "child_orgs": [
      {
        "org_id": "org_portco_a",
        "org_name": "Portco A",
        "total_volume": 1250000.00,
        "transaction_count": 847,
        "approval_rate": 0.94,
        "compliance_flags": 3,
        "avg_settlement_ms": 1240,
        "total_wallet_balance": 340000.00
      },
      {
        "org_id": "org_portco_b",
        "org_name": "Portco B",
        "total_volume": 890000.00,
        "transaction_count": 612,
        "approval_rate": 0.97,
        "compliance_flags": 1,
        "avg_settlement_ms": 980,
        "total_wallet_balance": 215000.00
      }
    ],
    "fund_totals": {
      "total_volume": 2140000.00,
      "transaction_count": 1459,
      "approval_rate": 0.95,
      "compliance_flags": 4,
      "total_wallet_balance": 555000.00
    }
  }
}
```

### Portco Administrator View

Portco-level administrators see full transaction detail for their own organization
and aggregate-only views of their child organizations (if any).

**Available at portco level:**

- Full transaction records for the portco's own org
- Individual agent wallet balances
- Authorization decision details
- Transaction metadata and descriptions
- Aggregate metrics for child divisions/branches (if any)

**Not available at portco level:**

- Transaction records from sibling portcos
- Fund-level aggregate data
- Other portco wallet balances
- Other portco agent details

### Reporting Access Control Matrix

| Viewer Level | Own Org Detail | Child Org Detail | Child Org Aggregate | Sibling Data |
| ------------ | -------------- | ---------------- | ------------------- | ------------ |
| Fund Admin   | Yes            | No               | Yes                 | N/A          |
| Portco Admin | Yes            | No               | Yes (if children)   | No           |
| Division     | Yes            | No               | Yes (if children)   | No           |
| Branch       | Yes            | N/A              | N/A                 | No           |

---

## Wallet Isolation

### Per-Agent Per-Org Wallets

Every agent in every organization has its own isolated wallet. Wallets are scoped
to the combination of `(org_id, agent_id, currency)`.

```
Org: Portco A (org_portco_a)
  |
  +-- agent-treasury-ops
  |     +-- Wallet: USD (available: $50,000, held: $5,000)
  |     +-- Wallet: EUR (available: EUR 12,000, held: EUR 0)
  |
  +-- agent-vendor-pay
  |     +-- Wallet: USD (available: $25,000, held: $2,500)
  |
  +-- agent-payroll
  |     +-- Wallet: USD (available: $100,000, held: $0)
  |
  ... (12 more agents)

Org: Portco B (org_portco_b)
  |
  +-- agent-treasury-ops  (DIFFERENT wallet from Portco A's treasury-ops)
  |     +-- Wallet: USD (available: $35,000, held: $0)
  |
  ... (14 more agents)
```

### Wallet Isolation Rules

1. **No cross-org wallet access**: An API key for Org A cannot read or modify
   wallets belonging to Org B, even if the agent IDs are identical.

2. **No cross-agent wallet access**: Agent A's wallet balance is never accessible
   to Agent B within the same org (agents transact, they do not inspect peer wallets).

3. **Settlement uses service role**: Cross-org fund transfers are executed by the
   settlement engine using the service role, which directly debits the sender wallet
   and credits the receiver wallet in a single database transaction.

4. **Escrow holds are wallet-scoped**: When funds are held in escrow, they are
   deducted from the agent's `available_balance` and added to `held_balance` within
   the same wallet record. No separate escrow wallet exists.

### Wallet Record Structure

```json
{
  "id": "wal_a1b2c3",
  "org_id": "org_portco_a",
  "agent_id": "agent-treasury-ops",
  "currency": "USD",
  "available_balance": 50000.00,
  "held_balance": 5000.00,
  "lifetime_sent": 1250000.00,
  "lifetime_received": 1350000.00,
  "last_transaction_at": "2026-04-14T12:35:00.000Z",
  "is_active": true,
  "created_at": "2026-01-15T00:00:00.000Z",
  "updated_at": "2026-04-14T12:35:00.000Z"
}
```

### Balance Invariant

The following invariant is enforced at the database level via a CHECK constraint:

```
available_balance >= 0
held_balance >= 0
available_balance + held_balance = total_balance
```

No operation can cause `available_balance` to go negative. If a transaction would
exceed the available balance, it is denied with reason code `insufficient_balance`.

---

## Scale Characteristics

### Reference Deployment

A typical PE fund deployment with 30 portfolio companies:

| Metric                          | Value                              |
| ------------------------------- | ---------------------------------- |
| Portfolio companies             | 30                                 |
| Agents per portco               | 15                                 |
| Total agents                    | 450                                |
| Transactions per agent per week | 10                                 |
| Total autonomous tx per week    | 4,500                              |
| Total autonomous tx per month   | ~19,500                            |
| Total autonomous tx per year    | ~234,000                           |

### Database Impact

| Resource                | Per Transaction | Weekly Total (4,500 tx) |
| ----------------------- | --------------- | ----------------------- |
| Transactions            | 1 row           | 4,500 rows              |
| Authorizations          | 1 row           | 4,500 rows              |
| Events                  | 2-5 rows        | 9,000 - 22,500 rows     |
| Wallets                 | 2 updates       | 9,000 updates           |
| Compliance evaluations  | 1 per tx        | 4,500 evaluations       |
| Deliveries              | 1-3 per tx      | 4,500 - 13,500 rows     |

### Performance Targets

| Operation                     | Target Latency  | P99 Latency      |
| ----------------------------- | --------------- | ---------------- |
| Policy resolution             | < 10ms          | < 25ms           |
| Compliance precheck           | < 500ms         | < 2000ms         |
| Authorization pipeline (full) | < 800ms         | < 3000ms         |
| Settlement execution          | < 200ms         | < 500ms          |
| Webhook delivery (first)      | < 5s            | < 15s            |
| Roll-up report generation     | < 2s            | < 5s             |

### Scaling Beyond 30 Portcos

The architecture scales horizontally with org count:

- **Database**: Row-level isolation means adding portcos adds rows but does not
  change query complexity (all queries filter on `org_id` using indexed columns).
- **Authorization pipeline**: Stateless -- each transaction authorization is
  independent and can be parallelized.
- **Compliance engine**: Evaluation is per-transaction and does not scale with
  org count.
- **Webhook delivery**: Per-endpoint, per-event -- adding orgs adds endpoints
  but delivery is parallel.

For deployments exceeding 100 portcos or 50,000 transactions per week, the platform
supports read replicas for reporting queries and partitioned tables by org_id for
write-heavy workloads.

---

## Configuration Examples

### Setting Up a New Portco

1. Create the organization as a child of the fund:

```bash
# Organization creation is done via the platform admin interface
# The fund admin creates a new child org with type "portfolio"
```

2. Create a default spending policy for the portco:

```bash
curl -X POST https://your-instance.pulse.app/pulse-api/policies \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "policy_name": "New Portco Default",
    "max_per_transaction": 5000,
    "max_daily": 25000,
    "max_monthly": 250000,
    "currency": "USD",
    "require_human_above": 10000,
    "compliance_precheck": true,
    "compliance_jurisdictions": ["US_FEDERAL"]
  }'
```

3. Fund agent wallets for the portco:

```bash
curl -X POST https://your-instance.pulse.app/pulse-api/wallets/agent-treasury-ops/fund \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"amount": 100000, "currency": "USD"}'
```

4. Optionally create agent-specific policies that override the default:

```bash
curl -X POST https://your-instance.pulse.app/pulse-api/policies \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "policy_name": "High-Value Treasury Agent",
    "agent_id": "agent-treasury-ops",
    "max_per_transaction": 50000,
    "max_daily": 200000,
    "max_monthly": 2000000,
    "require_human_above": 100000,
    "compliance_precheck": true,
    "compliance_jurisdictions": ["US_FEDERAL", "US_STATE_NY"]
  }'
```

### Cross-Org Transaction Example

Agent in Portco A pays agent in Portco B:

```bash
curl -X POST https://your-instance.pulse.app/pulse-api/payments/request \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "requesting_agent_id": "agent-treasury-ops",
    "counterparty_agent_id": "agent-vendor-pay",
    "counterparty_org_id": "org_portco_b",
    "amount": 15000,
    "currency": "USD",
    "tx_type": "intercompany_transfer",
    "category": "operations",
    "description": "Q2 shared services allocation"
  }'
```

The authorization pipeline evaluates both Portco A's sender policy and Portco B's
receiver policy. Both must approve for the transfer to settle.

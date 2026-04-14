# A2A Payment Protocol -- Architecture Overview

Version: 1.0.0
Status: Production
Last Updated: 2026-04-14

---

## 1. Three-Layer Architecture Model

The A2A Payment Protocol operates on a strict three-layer architecture designed
for defense-in-depth, deterministic authorization, and full auditability. Every
payment request traverses all three layers in sequence. No layer may be bypassed.

```
                    External Clients
                          |
                          v
            +--------------------------+
            |   Pulse API Gateway      |   Layer 1
            |   30 routes, SHA-256     |
            |   IP whitelist, limits   |
            +--------------------------+
                          |
                          v
            +--------------------------+
            |   Payment Agent Layer    |   Layer 2
            |   Agents #43, #44, #45  |
            |   13 payment routes      |
            |   9 permission scopes    |
            +--------------------------+
                          |
                          v
            +--------------------------+
            |   Core Platform          |   Layer 3
            |   45 agents, 93 conns    |
            |   21 verticals           |
            |   Sovereign Intelligence |
            +--------------------------+
```

---

## 2. Layer 1 -- Pulse API Gateway

### 2.1 Route Inventory

The gateway exposes exactly 30 routes under the `/pulse-api/` prefix. All routes
accept JSON request bodies and return JSON responses. The gateway performs no
business logic; it authenticates, rate-limits, and forwards.

| Category         | Route                                        | Method | Description                          |
|------------------|----------------------------------------------|--------|--------------------------------------|
| Auth             | `/pulse-api/auth/token`                      | POST   | Issue bearer token                   |
| Auth             | `/pulse-api/auth/refresh`                    | POST   | Refresh bearer token                 |
| Auth             | `/pulse-api/auth/revoke`                     | POST   | Revoke token                         |
| Payments         | `/pulse-api/payments/request`                | POST   | Initiate payment authorization       |
| Payments         | `/pulse-api/payments/execute`                | POST   | Execute authorized payment           |
| Payments         | `/pulse-api/payments/cancel`                 | POST   | Cancel pending payment               |
| Payments         | `/pulse-api/payments/status`                 | GET    | Query payment status                 |
| Payments         | `/pulse-api/payments/history`                | GET    | List payment history                 |
| Payments         | `/pulse-api/payments/receipt`                | GET    | Retrieve settlement receipt          |
| Payments         | `/pulse-api/payments/escrow/hold`            | POST   | Place funds in escrow                |
| Payments         | `/pulse-api/payments/escrow/release`         | POST   | Release escrowed funds               |
| Payments         | `/pulse-api/payments/escrow/dispute`         | POST   | Initiate escrow dispute              |
| Payments         | `/pulse-api/payments/webhook/register`       | POST   | Register settlement webhook          |
| Payments         | `/pulse-api/payments/webhook/deregister`     | POST   | Remove settlement webhook            |
| Payments         | `/pulse-api/payments/refund`                 | POST   | Initiate refund                      |
| Payments         | `/pulse-api/payments/batch`                  | POST   | Batch payment submission             |
| Orgs             | `/pulse-api/orgs/list`                       | GET    | List organizations                   |
| Orgs             | `/pulse-api/orgs/detail`                     | GET    | Organization detail                  |
| Orgs             | `/pulse-api/orgs/children`                   | GET    | List child organizations             |
| Orgs             | `/pulse-api/orgs/policy`                     | GET    | Read spending policy                 |
| Orgs             | `/pulse-api/orgs/policy`                     | PUT    | Update spending policy               |
| Agents           | `/pulse-api/agents/list`                     | GET    | List registered agents               |
| Agents           | `/pulse-api/agents/detail`                   | GET    | Agent detail                         |
| Agents           | `/pulse-api/agents/permissions`              | GET    | Agent permission scopes              |
| Agents           | `/pulse-api/agents/register`                 | POST   | Register new agent                   |
| Wallets          | `/pulse-api/wallets/balance`                 | GET    | Query wallet balance                 |
| Wallets          | `/pulse-api/wallets/ledger`                  | GET    | Ledger entries for wallet            |
| Wallets          | `/pulse-api/wallets/freeze`                  | POST   | Freeze wallet                        |
| Compliance       | `/pulse-api/compliance/check`                | POST   | Run compliance precheck              |
| Compliance       | `/pulse-api/compliance/report`               | GET    | Retrieve compliance report           |

### 2.2 Authentication -- SHA-256 HMAC

Every request to the gateway must include an `Authorization` header containing
an HMAC-SHA256 signature computed over the canonical request string.

```
canonical_string = HTTP_METHOD + "\n"
                 + REQUEST_PATH + "\n"
                 + SORTED_QUERY_STRING + "\n"
                 + SHA256(REQUEST_BODY) + "\n"
                 + TIMESTAMP_ISO8601

signature = HMAC-SHA256(api_secret, canonical_string)
header    = "PULSE-HMAC-SHA256 KeyId={api_key_id}, Signature={signature}, Timestamp={ts}"
```

The gateway rejects any request whose timestamp deviates more than 300 seconds
from server time (clock-skew tolerance). Replay protection is enforced by
storing a rolling window of seen signatures for 600 seconds.

### 2.3 IP Whitelist

Each API key is bound to a CIDR whitelist at registration time. The gateway
evaluates the source IP against the whitelist before any further processing.
Requests from non-whitelisted IPs receive `403 Forbidden` with no body.

### 2.4 Rate Limiting

Rate limits are enforced per API key using a sliding-window counter algorithm
backed by an in-memory store with persistence checkpoints every 60 seconds.

| Tier       | Requests/min | Burst  | Payment routes | Notes                     |
|------------|-------------|--------|----------------|---------------------------|
| Standard   | 120         | 30     | 30/min         | Default tier               |
| Elevated   | 600         | 100    | 120/min        | Requires approval          |
| Platform   | 3000        | 500    | 600/min        | Internal platform agents   |

When a rate limit is exceeded, the gateway returns `429 Too Many Requests` with
a `Retry-After` header indicating seconds until the window resets.

---

## 3. Layer 2 -- Payment Agent Layer

### 3.1 Agent Registry

Three dedicated payment agents handle all payment lifecycle operations.

| Agent ID | Name                   | Role                                                    |
|----------|------------------------|---------------------------------------------------------|
| #43      | Payment Authorizer     | Evaluates authorization pipeline, issues auth decisions |
| #44      | Payment Executor       | Executes settled transactions, manages wallet mutations |
| #45      | Payment Auditor        | Records immutable audit trail, validates settlement     |

### 3.2 Thirteen Payment Routes

The Payment Agent Layer exposes 13 internal routes consumed by the gateway.
These routes are not directly accessible from external clients.

| Route ID | Route Name                     | Source Agent | Target Agent | Description                                    |
|----------|--------------------------------|-------------|-------------|------------------------------------------------|
| PR-01    | `payment_request`              | Gateway     | #43         | Inbound authorization request                  |
| PR-02    | `authorization_decision`       | #43         | Gateway     | Auth approved or denied response               |
| PR-03    | `execute_payment`              | Gateway     | #44         | Trigger execution of authorized payment        |
| PR-04    | `execution_result`             | #44         | Gateway     | Execution success or failure                   |
| PR-05    | `settlement_event`             | #44         | #45         | Notify auditor of settlement                   |
| PR-06    | `audit_confirmation`           | #45         | #44         | Auditor confirms record                        |
| PR-07    | `escrow_hold_request`          | Gateway     | #44         | Request escrow hold                            |
| PR-08    | `escrow_release_request`       | Gateway     | #44         | Request escrow release                         |
| PR-09    | `escrow_dispute_request`       | Gateway     | #44         | Request escrow dispute                         |
| PR-10    | `refund_request`               | Gateway     | #44         | Initiate refund                                |
| PR-11    | `batch_payment_request`        | Gateway     | #43         | Batch authorization                            |
| PR-12    | `compliance_precheck`          | #43         | Compliance  | Request compliance scan                        |
| PR-13    | `escalation_required`          | #43         | Dispatcher  | Human escalation for high-value payments       |

### 3.3 Nine Permission Scopes

Each agent is granted a subset of the nine payment permission scopes.

| Scope                      | #43 | #44 | #45 | Description                                |
|----------------------------|-----|-----|-----|--------------------------------------------|
| `payments.authorize`       | yes | no  | no  | Issue authorization decisions               |
| `payments.execute`         | no  | yes | no  | Execute wallet mutations                    |
| `payments.audit.write`     | no  | no  | yes | Write audit records                         |
| `payments.audit.read`      | yes | yes | yes | Read audit records                          |
| `payments.escrow.manage`   | no  | yes | no  | Hold, release, dispute escrow               |
| `payments.refund`          | no  | yes | no  | Process refunds                             |
| `payments.compliance.read` | yes | no  | yes | Read compliance results                     |
| `payments.policy.read`     | yes | no  | no  | Read spending policies                      |
| `payments.wallet.read`     | yes | yes | yes | Read wallet balances                        |

---

## 4. Layer 3 -- Core Platform

### 4.1 Agent Ecosystem

The core platform hosts 45 registered agents spanning 21 industry verticals.
Each agent communicates exclusively through the inter-agent messaging bus.
Agents do not share memory, state, or database connections.

| Vertical               | Agent Count | Connector Count | Notes                        |
|------------------------|------------|-----------------|------------------------------|
| Real Estate            | 6          | 12              | Property hub-and-spoke model |
| Financial Services     | 5          | 9               | PE fund flows                |
| Healthcare             | 3          | 7               | HIPAA-scoped connectors      |
| Legal                  | 3          | 5               | Attorney-client privilege    |
| Construction           | 3          | 6               | Draw scheduling              |
| Insurance              | 2          | 5               | Claims pipeline              |
| Hospitality            | 2          | 4               | Booking and revenue mgmt     |
| Retail                 | 2          | 5               | Inventory and POS            |
| Manufacturing          | 2          | 4               | Supply chain                 |
| Logistics              | 2          | 4               | Fleet and routing            |
| Agriculture            | 2          | 3               | Crop and commodity           |
| Energy                 | 1          | 3               | Grid and metering            |
| Education              | 1          | 3               | Enrollment and tuition       |
| Nonprofit              | 1          | 2               | Donor management             |
| Government             | 1          | 2               | Procurement                  |
| Media                  | 1          | 3               | Licensing and royalties      |
| Telecom                | 1          | 2               | Usage billing                |
| Automotive             | 1          | 3               | Dealer and fleet             |
| Fitness                | 1          | 2               | Membership billing           |
| Food & Beverage        | 1          | 2               | Supplier payments            |
| Professional Services  | 3          | 7               | Time and billing             |
| **Totals**             | **45**     | **93**          |                              |

### 4.2 Sovereign Intelligence

The Sovereign Intelligence subsystem operates as a multi-engine analytics layer
that learns from anonymized payment patterns across all organizations on the
platform. It never accesses raw transaction amounts or counterparty identities.
Instead, it ingests feature vectors derived from:

- Transaction velocity (payments per hour, per day, per week)
- Category distribution entropy
- Time-of-day clustering
- Counterparty diversity index
- Deviation from historical spending policy utilization

Sovereign Intelligence produces two outputs:

1. **Risk Score** (0.00 -- 1.00): Attached to every authorization request
   before it reaches the Payment Authorizer. A score above 0.85 triggers
   automatic escalation to a Property Dispatcher for human review.

2. **Policy Recommendations**: Weekly digest sent to organization admins
   suggesting spending policy adjustments based on observed patterns. These
   recommendations are advisory only and never auto-applied.

The multi-engine architecture processes these vectors through an ensemble of
Pulse Engines that specialize in anomaly detection, temporal pattern recognition,
and categorical drift analysis. Each engine votes independently, and the final
risk score is a weighted median of all engine outputs.

### 4.3 Predictive Compliance

Predictive Compliance scans every payment request against a jurisdiction rule
database covering 194 countries and 63 sub-national regulatory zones. The scan
evaluates:

- Sanctioned entity lists (updated every 4 hours)
- Cross-border transfer restrictions
- Currency control regulations
- Industry-specific payment caps
- Anti-money-laundering pattern thresholds

Results are returned as `pass` or `fail` with an array of matched rule IDs.
A `fail` result halts the authorization pipeline immediately and produces a
compliance denial reason code.

### 4.4 Scheduling Subsystem

The scheduling subsystem supports three scheduling primitives:

1. **Recurring Payments**: Cron-based scheduling with timezone-aware evaluation.
   Payments are queued 60 seconds before the scheduled time and submitted to
   the authorization pipeline at the exact scheduled moment.

2. **Deferred Payments**: Single-fire payments scheduled for a future date.
   The scheduler validates that the spending policy will permit the payment
   at the scheduled time by performing a dry-run authorization.

3. **Conditional Payments**: Payments triggered by an external event webhook.
   The scheduler holds the payment in `pending_trigger` state until the
   webhook fires, then submits it to the authorization pipeline.

### 4.5 Property Hub-and-Spoke Model

For the Real Estate vertical, the platform implements a hub-and-spoke model
where a central Property Dispatcher agent coordinates six satellite agents:

```
                  +---------------------+
                  | Property Dispatcher |  Hub
                  | (Escalation Target) |
                  +---------------------+
                 / |    |    |    |     \
                v  v    v    v    v      v
            Listing  Lease  Maint  Acct  Inspect  Close
            Agent    Agent  Agent  Agent Agent    Agent
```

The Property Dispatcher is the designated human escalation target for all
payment-related decisions that exceed automated authority. When the Payment
Authorizer (#43) determines that a payment requires human approval (amount
exceeds threshold, risk score above 0.85, or policy explicitly requires
human sign-off), it sends an `escalation_required` message to the Property
Dispatcher. The Dispatcher routes the decision to the appropriate human
stakeholder and returns the `human_decision` message to resume the pipeline.

---

## 5. Complete Inter-Agent Route Inventory (49 Routes)

All inter-agent communication is asynchronous, message-based, and idempotent.
Each route has a unique route ID, source agent, target agent, and payload schema.

### 5.1 Content Pipeline (10 Routes)

| Route ID | Route Name                     | Source         | Target          |
|----------|--------------------------------|----------------|-----------------|
| CP-01    | `content_draft_request`        | Content Writer | Editor          |
| CP-02    | `content_draft_response`       | Editor         | Content Writer  |
| CP-03    | `content_review_request`       | Editor         | Reviewer        |
| CP-04    | `content_review_response`      | Reviewer       | Editor          |
| CP-05    | `content_publish_request`      | Editor         | Publisher       |
| CP-06    | `content_publish_confirm`      | Publisher      | Editor          |
| CP-07    | `content_analytics_request`    | Publisher      | Analytics       |
| CP-08    | `content_analytics_response`   | Analytics      | Publisher       |
| CP-09    | `content_archive_request`      | Publisher      | Archiver        |
| CP-10    | `content_archive_confirm`      | Archiver       | Publisher       |

### 5.2 Proposal Pipeline (8 Routes)

| Route ID | Route Name                     | Source         | Target          |
|----------|--------------------------------|----------------|-----------------|
| PP-01    | `proposal_initiate`            | Sales Agent    | Proposal Gen    |
| PP-02    | `proposal_draft`               | Proposal Gen   | Sales Agent     |
| PP-03    | `proposal_pricing_request`     | Proposal Gen   | Pricing Engine  |
| PP-04    | `proposal_pricing_response`    | Pricing Engine | Proposal Gen    |
| PP-05    | `proposal_approval_request`    | Sales Agent    | Manager Agent   |
| PP-06    | `proposal_approval_response`   | Manager Agent  | Sales Agent     |
| PP-07    | `proposal_send`                | Sales Agent    | Delivery Agent  |
| PP-08    | `proposal_delivery_confirm`    | Delivery Agent | Sales Agent     |

### 5.3 Compliance Pipeline (7 Routes)

| Route ID | Route Name                     | Source             | Target              |
|----------|--------------------------------|--------------------|---------------------|
| CL-01    | `compliance_precheck`          | Payment Auth #43   | Predictive Compl.   |
| CL-02    | `compliance_result`            | Predictive Compl.  | Payment Auth #43    |
| CL-03    | `compliance_audit_log`         | Predictive Compl.  | Payment Auditor #45 |
| CL-04    | `compliance_rule_update`       | Rule Ingester      | Predictive Compl.   |
| CL-05    | `compliance_report_request`    | Admin Agent        | Predictive Compl.   |
| CL-06    | `compliance_report_response`   | Predictive Compl.  | Admin Agent         |
| CL-07    | `compliance_alert`             | Predictive Compl.  | Property Dispatcher |

### 5.4 Operational Signals (11 Routes)

| Route ID | Route Name                     | Source             | Target              |
|----------|--------------------------------|--------------------|---------------------|
| OS-01    | `heartbeat_ping`               | Any Agent          | Health Monitor      |
| OS-02    | `heartbeat_pong`               | Health Monitor     | Any Agent           |
| OS-03    | `config_update`                | Config Manager     | Any Agent           |
| OS-04    | `config_ack`                   | Any Agent          | Config Manager      |
| OS-05    | `metric_report`                | Any Agent          | Metrics Collector   |
| OS-06    | `alert_trigger`                | Metrics Collector  | Alert Router        |
| OS-07    | `alert_dispatch`               | Alert Router       | Property Dispatcher |
| OS-08    | `schedule_trigger`             | Scheduler          | Any Agent           |
| OS-09    | `schedule_ack`                 | Any Agent          | Scheduler           |
| OS-10    | `log_event`                    | Any Agent          | Log Aggregator      |
| OS-11    | `capability_announce`          | Any Agent          | Registry            |

### 5.5 Payment Pipeline (13 Routes)

These are the 13 payment-specific routes detailed in Section 3.2 above (PR-01
through PR-13), reproduced here for completeness of the 49-route inventory.

| Route ID | Route Name                     | Source         | Target          |
|----------|--------------------------------|----------------|-----------------|
| PR-01    | `payment_request`              | Gateway        | Auth #43        |
| PR-02    | `authorization_decision`       | Auth #43       | Gateway         |
| PR-03    | `execute_payment`              | Gateway        | Executor #44    |
| PR-04    | `execution_result`             | Executor #44   | Gateway         |
| PR-05    | `settlement_event`             | Executor #44   | Auditor #45     |
| PR-06    | `audit_confirmation`           | Auditor #45    | Executor #44    |
| PR-07    | `escrow_hold_request`          | Gateway        | Executor #44    |
| PR-08    | `escrow_release_request`       | Gateway        | Executor #44    |
| PR-09    | `escrow_dispute_request`       | Gateway        | Executor #44    |
| PR-10    | `refund_request`               | Gateway        | Executor #44    |
| PR-11    | `batch_payment_request`        | Gateway        | Auth #43        |
| PR-12    | `compliance_precheck`          | Auth #43       | Compliance      |
| PR-13    | `escalation_required`          | Auth #43       | Dispatcher      |

**Total: 10 + 8 + 7 + 11 + 13 = 49 inter-agent routes.**

---

## 6. Parent-Child Organization Hierarchy

The platform supports a hierarchical organization model designed for private
equity fund structures and multi-entity corporate groups.

### 6.1 Hierarchy Model

```
    +---------------------------+
    | Fund Entity (Parent Org)  |
    | - Master spending policy  |
    | - Consolidated reporting  |
    +---------------------------+
        |           |           |
        v           v           v
    +--------+  +--------+  +--------+
    | PortCo |  | PortCo |  | PortCo |
    | Alpha  |  | Beta   |  | Gamma  |
    | (Child)|  | (Child)|  | (Child)|
    +--------+  +--------+  +--------+
```

Each parent organization can have unlimited child organizations. A child
organization inherits the parent spending policy by default but may define
its own overrides. A child organization cannot create grandchildren; the
hierarchy is strictly two levels deep.

### 6.2 Spending Policy Cascade

Spending policies are evaluated in the following precedence order:

1. **Agent-Specific Policy**: If the requesting agent has a policy bound
   directly to it within the organization, that policy governs.
2. **Organization Default Policy**: If no agent-specific policy exists,
   the organization default policy governs.
3. **Parent Organization Policy**: If the child organization has no default
   policy, the parent organization default policy governs.
4. **Deny (no_policy)**: If no policy exists at any level, the payment is
   denied with reason code `no_policy`.

Policy fields include:

| Field                   | Type    | Description                                    |
|-------------------------|---------|------------------------------------------------|
| `daily_limit`           | decimal | Maximum daily spend (rolling 24h window)       |
| `monthly_limit`         | decimal | Maximum monthly spend (rolling 30-day window)  |
| `per_transaction_limit` | decimal | Maximum single transaction amount               |
| `allowed_categories`    | array   | Permitted spending categories                   |
| `blocked_counterparties`| array   | Counterparty IDs permanently blocked            |
| `approved_counterparties`| array  | Counterparty IDs pre-approved                  |
| `human_review_threshold`| decimal | Amount above which human review is required     |
| `currency`              | string  | ISO 4217 currency code                          |

### 6.3 Cross-Organization Transactions

When a payment flows between two organizations (e.g., PortCo Alpha pays PortCo
Beta), the authorization pipeline evaluates the spending policies of **both**
organizations:

1. The sender organization policy must permit the outbound payment (amount,
   category, counterparty, daily/monthly limits).
2. The receiver organization policy must permit the inbound receipt (the
   receiver may block certain counterparties or categories).

If either policy denies the transaction, the entire payment is denied. The
denial reason code indicates which side rejected the payment.

---

## 7. Deployment Topology

The three-layer architecture is deployed as isolated process groups with no
shared runtime. Layer 1 (Gateway) runs as a stateless HTTP server cluster behind
a load balancer. Layer 2 (Payment Agents) runs as long-lived processes consuming
from the inter-agent message bus. Layer 3 (Core Platform) agents each run as
independent processes with dedicated message queue subscriptions.

All inter-layer communication uses authenticated, encrypted channels. No layer
trusts any other layer implicitly; every message is validated against the
sender agent's registered public key before processing.

---

## 8. Appendix: Glossary

| Term                    | Definition                                                  |
|-------------------------|-------------------------------------------------------------|
| Pulse Engine            | A multi-engine processing unit within Sovereign Intelligence|
| Property Dispatcher     | Human escalation coordinator for the real estate vertical   |
| Spending Policy         | Configurable ruleset governing payment limits and categories|
| Authorization Pipeline  | The 10-step process evaluating every payment request        |
| Settlement              | The finalization of a payment with wallet balance mutations  |
| Escrow                  | Temporary fund hold pending fulfillment or dispute          |
| Counterparty            | The receiving entity in a payment transaction               |
| Risk Score              | 0.00-1.00 anomaly score from Sovereign Intelligence        |
| HMAC-SHA256             | Hash-based message authentication code using SHA-256        |
| Inter-Agent Route       | A named, typed message channel between two agents           |

# Authorization Protocol

Version: 2.0.0
Status: Production
Last Updated: 2026-04-14

---

## The Hardest Problem First: AUTH-CONCURRENT-001

Before anything else, we need to talk about the race condition that nearly cost us real money.

Picture two payment requests arriving 10ms apart. Both originate from the same agent within the same organization. The agent's daily spend sits at $900 against a $1,000 limit. Request A wants $200. Request B wants $200. Each request independently reads the current spend total of $900, calculates $900 + $200 = $1,100 -- wait, that exceeds $1,000, so it should be denied. But here is the problem: if both requests read $900 *before* either one writes its authorization record, both see $100 of remaining headroom. Both authorize $200? No -- both see $100 remaining and should deny. Actually, the more insidious variant: the spend is $800, the limit is $1,000, and both requests are for $150 each. Each reads $800, calculates $800 + $150 = $950, which is under $1,000, so both approve. Combined actual spend: $1,100. The limit is blown by $100 and nobody noticed until the audit trail caught it.

This is AUTH-CONCURRENT-001. We discovered it during load testing when we fired 50 concurrent authorization requests from a single agent and found the daily spend exceeded the configured limit by 340%. The root cause was a textbook time-of-check-to-time-of-use (TOCTOU) gap between reading the spend total and writing the new authorization record.

### Why Advisory Locks, Not Optimistic Locking

The obvious solution in most web applications is optimistic concurrency control: read the spend, attempt the write with a version check, retry if the version has changed. We rejected this for three reasons specific to payment authorization.

First, retry storms under contention. When an agent is actively making payments -- say, a procurement bot purchasing supplies from ten vendors in rapid succession -- optimistic locking generates a cascade of retries. Each retry re-reads the spend, re-evaluates the pipeline, and attempts the write again. Under moderate contention (5-10 concurrent requests), we measured retry rates of 60-80%. Under heavy contention, the system spent more time retrying than authorizing. The throughput curve inverted: more requests meant fewer successful authorizations per second.

Second, unpredictable latency. Payment systems have downstream dependencies that care about timing. An authorization that takes 150ms on the first attempt might take 900ms after two retries, and the caller has no way to predict which it will be. We watched external integrations timeout because authorization latency spiked from p50 of 160ms to p99 of 2.4 seconds during contention windows. Advisory locks give us deterministic wait times: you acquire the lock or you queue behind whoever holds it. The latency is a function of the lock hold duration (which we control tightly) rather than a function of random retry timing.

Third, determinism matters more than throughput. In a payment system, we would rather process 100 authorizations per second with perfect correctness than 500 per second with a 0.1% chance of exceeding a spend limit. Advisory locks serialize access to the spend calculation for a given agent-org pair. The lock is scoped narrowly -- agent ID plus organization ID -- so two different agents within the same org do not contend with each other. The lock is held only for the duration of the spend calculation and record creation, typically 15-40ms.

The implementation uses a keyed advisory lock where the key is derived from a hash of the agent ID and organization ID. This means the lock is in-memory, does not create row-level contention on the payment records table, and is automatically released if the holding connection drops.

```
-- Pseudocode for the advisory lock approach
key = hash(agent_id, org_id)

ACQUIRE advisory_lock(key)
    daily_spent = SUM(amounts) WHERE agent=agent_id AND org=org_id
                  AND status IN (settled, authorized, executing)
                  AND created_within_last_24_hours
    monthly_spent = SUM(amounts) WHERE same_filters
                    AND created_within_last_30_days

    IF daily_spent + requested_amount > daily_limit THEN
        RELEASE advisory_lock(key)
        RETURN denial(daily_limit_exceeded)
    END IF

    IF monthly_spent + requested_amount > monthly_limit THEN
        RELEASE advisory_lock(key)
        RETURN denial(monthly_limit_exceeded)
    END IF

    WRITE authorization_record(...)
RELEASE advisory_lock(key)
```

We benchmarked this against `SERIALIZABLE` isolation with `FOR UPDATE` locks. Advisory locks were 3x faster under contention because they avoid the overhead of row-level lock escalation on the payment records. The tradeoff is that advisory locks are connection-scoped, so connection pooling configuration matters -- we pin connections for the duration of the lock hold to prevent premature release.

---

## The 10-Step Pipeline

With the concurrency problem solved, here is how the full authorization pipeline works. Every payment request entering the system passes through these ten steps in strict sequence. There is no branching, no parallel execution, no short-circuiting except on failure. If a step fails, the pipeline stops and returns a denial with a reason code. If a step passes, the next step begins.

We chose strict sequencing over parallel evaluation (where you might run counterparty checks and category checks simultaneously) because the steps have implicit data dependencies that are easy to miss. For example, the policy resolved in Step 1 determines the limits checked in Steps 2-4 and the counterparty lists checked in Step 5. Running them in parallel would require passing the policy object to all parallel branches, and a bug in the policy resolution path would manifest as inconsistent denials rather than a clean failure. Sequential execution is slower by maybe 20ms but vastly easier to reason about and debug.

### Step 1: Policy Resolution

The pipeline starts by figuring out which spending policy governs this request. We resolve policies through a three-level cascade: agent-specific policy first, then organization default, then parent organization default. If nothing exists at any level, the request is denied with `no_policy`.

The cascade exists because organizations have different needs. A large org might set a generous default policy for most agents but restrict a specific agent that handles petty cash to a $500 daily limit. A child organization might inherit its parent's policy until it configures its own. The resolution order -- most specific wins -- follows the principle of least surprise.

```
-- Pseudocode: policy resolution cascade
policy = LOOKUP active_policy
         WHERE agent = requesting_agent AND org = requesting_org
IF policy IS NULL THEN
    policy = LOOKUP active_policy
             WHERE agent IS NULL AND org = requesting_org
END IF
IF policy IS NULL AND org_has_parent THEN
    policy = LOOKUP active_policy
             WHERE agent IS NULL AND org = parent_org
END IF
IF policy IS NULL THEN
    DENY with reason_code = no_policy
END IF
```

One thing worth noting: the resolved policy is snapshotted at this point. We freeze the policy object as it exists at the moment of resolution. If an admin updates the policy while the pipeline is executing (which takes 150-500ms typically), the in-flight authorization uses the old policy. This is intentional -- see the Design Decisions section below for why.

The policy object carries everything the rest of the pipeline needs:

```json
{
  "policy_id": "pol_a1b2c3d4",
  "org_id": "org_x9y8z7",
  "agent_id": null,
  "daily_limit": 50000.00,
  "monthly_limit": 500000.00,
  "per_transaction_limit": 25000.00,
  "allowed_categories": ["vendor_payment", "contractor", "utilities", "supplies"],
  "blocked_counterparties": ["cp_blocked_001", "cp_blocked_002"],
  "approved_counterparties": ["cp_approved_001", "cp_approved_002"],
  "human_review_threshold": 10000.00,
  "currency": "USD",
  "active": true,
  "created_at": "2026-01-15T08:00:00Z",
  "updated_at": "2026-03-20T14:30:00Z"
}
```

### Step 2: Amount Validation

Three checks against the resolved policy:

- If `amount > per_transaction_limit`, deny with `amount_exceeds_limit`.
- If `amount <= 0`, deny with `invalid_amount`.
- If the payment currency does not match the policy currency, deny with `currency_mismatch`.

We do not do currency conversion. If the policy says USD and the request says EUR, it is denied. Cross-currency payments require explicit policy configuration. We made this decision after watching a currency conversion bug in a staging environment silently approve a payment for 10x the intended amount because the conversion rate was stale. Hard currency matching eliminates that entire class of bug.

### Step 3: Daily Spend Calculation

This is where the advisory lock from AUTH-CONCURRENT-001 kicks in. We acquire the lock scoped to the agent-org pair, then sum all payments in `settled`, `authorized`, or `executing` status created within the last 24 hours.

The rolling 24-hour window is important. We deliberately avoided calendar-day boundaries because they create a gaming vector: an agent at $49,000 of a $50,000 daily limit at 23:58 could authorize a $50,000 payment at 00:01 if the window reset at midnight. The rolling window means a payment authorized at 14:30 on Tuesday counts against the limit until 14:30 on Wednesday.

We include `authorized` and `executing` statuses in the sum, not just `settled`. If we only counted settled payments, an agent could authorize 20 payments in rapid succession (all reading the same settled total) and then settle them sequentially, blowing through the limit. Including pre-settled statuses closes that gap.

```
-- Pseudocode inside the advisory lock
daily_spent = SUM(amount)
    FROM payment_records
    WHERE agent = requesting_agent
      AND org = requesting_org
      AND status IN (settled, authorized, executing)
      AND created_at >= NOW() - INTERVAL 24 hours

daily_remaining = policy.daily_limit - daily_spent
IF requested_amount > daily_remaining THEN
    DENY with reason_code = daily_limit_exceeded
END IF
```

### Step 4: Monthly Spend Calculation

Same mechanics as the daily calculation, same advisory lock scope, but using a 30-day rolling window. Both the daily and monthly checks happen within the same lock hold, so there is no window between them where another request could sneak in.

```
monthly_spent = SUM(amount)
    FROM payment_records
    WHERE agent = requesting_agent
      AND org = requesting_org
      AND status IN (settled, authorized, executing)
      AND created_at >= NOW() - INTERVAL 30 days

monthly_remaining = policy.monthly_limit - monthly_spent
IF requested_amount > monthly_remaining THEN
    DENY with reason_code = monthly_limit_exceeded
END IF
```

### Step 5: Counterparty Validation

We check the target counterparty against two lists: blocked and approved. The evaluation order is blocked-first, approved-second, and this is non-negotiable. If a counterparty appears on both lists (which indicates a data inconsistency that should be fixed separately), blocked wins. Security over convenience -- see Design Decisions.

```
IF counterparty_id IN policy.blocked_counterparties THEN
    DENY with reason_code = counterparty_blocked
END IF

IF policy.approved_counterparties IS NOT EMPTY THEN
    IF counterparty_id NOT IN policy.approved_counterparties THEN
        DENY with reason_code = counterparty_not_approved
    END IF
END IF
```

When the approved list is empty, any non-blocked counterparty is allowed. This is the default posture for new organizations -- open by default, with the ability to restrict later. Organizations that want a closed posture populate the approved list on day one.

For cross-organization payments, we also check the receiver's policy. The receiver org might block incoming payments from specific senders. From the receiver's perspective, the sender is the counterparty.

```
receiver_policy = resolve_policy(receiver_org_id, null)
IF sender_org_id IN receiver_policy.blocked_counterparties THEN
    DENY with reason_code = receiver_counterparty_blocked
END IF
```

### Step 6: Category Validation

The payment category is checked against the policy's allowed categories list. If the list is empty, all categories are permitted. If the list is populated, the payment category must be in it.

```
IF policy.allowed_categories IS NOT EMPTY THEN
    IF payment.category NOT IN policy.allowed_categories THEN
        DENY with reason_code = category_not_allowed
    END IF
END IF
```

Categories are standardized strings from a platform-wide registry. Organizations can register custom categories but they must not collide with standard codes. We enforce this at registration time, not at authorization time, because a collision check during authorization would add latency to every request for a condition that should never occur.

### Step 7: Wallet Balance Check

We verify the sender's wallet has sufficient available balance. The available balance is the total wallet balance minus all holds: authorized-but-unsettled payments, escrow holds, and pending executions. This prevents double-spending.

```
available_balance = LOOKUP wallet_available_balance
    WHERE org = sender_org

IF requested_amount > available_balance THEN
    DENY with reason_code = insufficient_funds
END IF
```

The wallet balance check uses its own lock (separate from the spend calculation lock) because the wallet is org-scoped, not agent-scoped. Two agents within the same org contend on the wallet lock, which is correct behavior -- the org's wallet is a shared resource.

### Step 8: Human Escalation (Conditional)

This step only fires when either (a) the payment amount exceeds the policy's `human_review_threshold`, or (b) the risk score exceeds 0.85. When neither condition is met, the step is a no-op and adds zero latency.

When escalation is required, the pipeline pauses. We set the payment status to `pending_human_review` and send an escalation message to the Property Dispatcher for the organization. The human reviewer gets the full context: amount, counterparty, category, risk score, policy details. They approve or deny.

```
requires_escalation = false

IF amount > policy.human_review_threshold THEN
    requires_escalation = true
    escalation_reason = amount_exceeds_threshold
END IF

IF risk_score > 0.85 THEN
    requires_escalation = true
    escalation_reason = high_risk_score
END IF

IF requires_escalation THEN
    SET payment status = pending_human_review
    SEND escalation_required TO property_dispatcher
    WAIT FOR human_decision (timeout: configurable, default 72 hours)

    IF human_decision = denied THEN
        DENY with reason_code = human_denied
    END IF
    IF no_decision_within_timeout THEN
        DENY with reason_code = escalation_timeout
    END IF
END IF
```

The timeout is configurable per organization, minimum 1 hour, maximum 168 hours (7 days). We chose 72 hours as the default because it covers a long weekend without being so long that authorized-but-unreviewed payments pile up indefinitely.

### Step 9: Compliance Precheck

The authorization agent sends a compliance precheck request to the Predictive Compliance subsystem. This evaluates the payment against sanctioned entity lists (OFAC SDN, EU consolidated, UN Security Council, plus 17 additional national lists), cross-border transfer restrictions, anti-money-laundering thresholds, and industry-specific caps.

```json
{
  "payment_id": "pay_abc123",
  "sender_org_id": "org_x9y8z7",
  "sender_jurisdiction": "US-CA",
  "receiver_org_id": "org_m3n4o5",
  "receiver_jurisdiction": "GB",
  "amount": 15000.00,
  "currency": "USD",
  "category": "vendor_payment",
  "counterparty_id": "cp_xyz789"
}
```

If the compliance scan returns a failure, the pipeline terminates with `compliance_denied`. The matched rules are recorded in the authorization log for audit purposes, but they are not returned to the caller in full detail -- we return only the reason code and a generic description. Leaking specific rule matches to callers could enable adversarial probing of our compliance ruleset.

A successful compliance result looks like this:

```json
{
  "payment_id": "pay_abc123",
  "result": "pass",
  "matched_rules": [],
  "scan_duration_ms": 145,
  "scanned_at": "2026-04-14T10:35:24Z"
}
```

A failure includes the matched rules internally:

```json
{
  "payment_id": "pay_abc123",
  "result": "fail",
  "matched_rules": [
    {
      "rule_id": "OFAC-SDN-2026-04",
      "description": "Counterparty appears on OFAC SDN list",
      "severity": "blocking"
    }
  ],
  "scan_duration_ms": 88,
  "scanned_at": "2026-04-14T10:35:24Z"
}
```

### Step 10: Authorization Record and Decision

If every preceding step passed, we create the authorization record and return approval. The record captures the full state at decision time: spend before and after, wallet balance before and after, risk score, compliance result, whether human review was required, and the pipeline duration.

```json
{
  "authorization_id": "auth_def456",
  "payment_id": "pay_abc123",
  "decision": "approved",
  "reason_code": null,
  "policy_id": "pol_a1b2c3d4",
  "policy_resolution_path": "agent_specific",
  "amount": 15000.00,
  "currency": "USD",
  "sender_org_id": "org_x9y8z7",
  "receiver_org_id": "org_m3n4o5",
  "counterparty_id": "cp_xyz789",
  "category": "vendor_payment",
  "daily_spent_before": 22000.00,
  "daily_spent_after": 37000.00,
  "monthly_spent_before": 185000.00,
  "monthly_spent_after": 200000.00,
  "wallet_balance_before": 75000.00,
  "wallet_balance_after": 60000.00,
  "risk_score": 0.32,
  "compliance_result": "pass",
  "human_review_required": false,
  "pipeline_duration_ms": 312,
  "authorized_at": "2026-04-14T10:35:25Z",
  "expires_at": "2026-04-14T11:35:25Z"
}
```

Authorizations expire after 60 minutes by default. If the payment is not executed within this window, the authorization is voided and the held amount is released from spend calculations. The expiry window is configurable per organization (minimum 5 minutes, maximum 24 hours). We set the default at 60 minutes because it balances the need for prompt execution against the reality that some settlement flows involve human approval steps on the receiver side.

---

## Design Decisions

This section documents the tradeoffs we made and why. These are not accidental -- each one was debated, sometimes heatedly, and represents a deliberate choice.

### Why Blocked Is Checked Before Approved

In Step 5, we check the blocked counterparty list before the approved list. This means that if a counterparty somehow appears on both lists, the blocked check catches it first and denies the payment. The alternative -- checking approved first -- would allow payments to blocked counterparties as long as they were also on the approved list.

We chose security over convenience. A counterparty appearing on both lists is a data integrity issue that should be flagged and fixed. But while it exists, the safe default is to deny. In a payment system, a false denial is an inconvenience (the payment can be retried after fixing the list). A false approval is potentially irrecoverable -- the funds are gone, the counterparty may be sanctioned or fraudulent, and unwinding the transaction may be impossible.

We considered adding a validation check at policy-save time to reject policies where a counterparty appears on both lists. We ultimately added it as a warning rather than a hard block, because there are legitimate transient states during policy migration where a counterparty is being moved from approved to blocked and briefly appears on both. The blocked-first evaluation order makes this transient state safe without requiring complex migration tooling.

### Why Policy Snapshots Are Frozen at Decision Time

When Step 1 resolves a policy, we snapshot it. The rest of the pipeline uses that snapshot, even if the underlying policy is modified during pipeline execution. We do not re-read the policy at each step.

This is an audit immutability decision. The authorization record includes the `policy_id` that governed the decision. If we allowed the policy to change mid-pipeline, the authorization record would reference a policy that did not actually govern all steps of the decision. An auditor reviewing the record would see a policy with a $50,000 daily limit and an authorization that was approved despite $48,000 in daily spend, not knowing that at the time of the spend calculation, the limit was $60,000 and was lowered to $50,000 during the compliance check.

Frozen snapshots mean the authorization record is self-consistent. The policy that governed the decision is the policy recorded in the decision. Period.

The downside: if an admin lowers a limit to respond to a fraud alert, in-flight authorizations that already passed the old limit will still be approved. We accept this because (a) the authorization window is short (150-500ms for non-escalated payments), (b) the admin can void the authorization before settlement, and (c) the alternative -- re-reading the policy at each step -- adds 5-10ms of latency per step and introduces a class of bugs where different steps see different policy versions.

### Why the Compliance Precheck Is Synchronous (For Now)

The compliance precheck in Step 9 is the most expensive step in the pipeline, averaging 100-150ms. It is also the most amenable to being made asynchronous -- we could authorize the payment optimistically and run the compliance check in the background, blocking only at settlement time.

We chose to keep it synchronous for now because the regulatory cost of authorizing a payment to a sanctioned entity, even if we catch it before settlement, is nonzero. Some compliance frameworks require that the authorization itself be denied, not just the settlement. We would rather pay the latency cost than navigate the regulatory gray area.

That said, the pipeline is designed to make this step async-compatible. The compliance precheck is the second-to-last step, it has no side effects on the spend calculations, and its result is a simple pass/fail that gates the final authorization record creation. If regulatory guidance clarifies that catching sanctions at settlement time is sufficient, we can move this step to a background check with minimal code changes. We built the interface with `async_compatible: true` in the internal configuration, but the feature flag is currently off.

This is future-proofing without over-engineering. We did not build the async path, the queue infrastructure, or the background worker. We just made sure the synchronous implementation does not create coupling that would make the async path difficult later.

---

## Reason Codes

The authorization pipeline uses 11 standardized reason codes. Every denial includes exactly one reason code corresponding to the first step that failed.

| Code | Pipeline Step | What It Means |
|------|--------------|---------------|
| `no_policy` | 1 - Policy Resolution | No spending policy found at any cascade level. The agent has no policy, the org has no default, and there is no parent org policy. |
| `amount_exceeds_limit` | 2 - Amount Validation | The requested amount exceeds the per-transaction limit defined in the resolved policy. |
| `invalid_amount` | 2 - Amount Validation | The amount is zero, negative, or not a valid decimal number. |
| `currency_mismatch` | 2 - Amount Validation | The payment currency does not match the policy currency. No conversion is attempted. |
| `daily_limit_exceeded` | 3 - Daily Spend | Adding this payment to the rolling 24-hour spend total would exceed the daily limit. |
| `monthly_limit_exceeded` | 4 - Monthly Spend | Adding this payment to the rolling 30-day spend total would exceed the monthly limit. |
| `counterparty_blocked` | 5 - Counterparty | The target counterparty is on the sender's blocked counterparty list. |
| `counterparty_not_approved` | 5 - Counterparty | The sender enforces an approved counterparty list and the target is not on it. |
| `receiver_counterparty_blocked` | 5 - Counterparty | The receiver org has blocked the sender org as a counterparty. |
| `category_not_allowed` | 6 - Category | The payment category is not in the policy's allowed categories list. |
| `insufficient_funds` | 7 - Wallet Balance | The sender wallet's available balance (after holds) is less than the payment amount. |
| `human_denied` | 8 - Human Escalation | A human reviewer explicitly denied the payment. |
| `escalation_timeout` | 8 - Human Escalation | No human decision was received within the configured timeout window. |
| `compliance_denied` | 9 - Compliance | The Predictive Compliance scan returned a blocking rule match. |

Reason codes are intentionally terse. We do not embed sensitive information (like which sanctions list matched or how close the spend is to the limit) in the reason code or the denial response. Detailed information is logged internally for audit and support purposes.

---

## Idempotency

Every authorization request must include an `idempotency_key`. If the gateway receives a request with an idempotency key that has been seen within the last 24 hours, it returns the cached original response without re-executing the pipeline.

This matters because network retries are inevitable. A client that sends a request and gets a timeout does not know whether the request was processed. Without idempotency, retrying could authorize the payment twice (doubling the spend). With idempotency, the retry returns the original decision.

Idempotency keys are scoped to the API key. Two different API keys can use the same idempotency key string without conflict. The cache TTL of 24 hours was chosen to exceed the maximum authorization expiry window (24 hours), ensuring that a retry within the authorization window always hits the cache.

---

## Pipeline Timing

Under normal conditions the pipeline completes in under 500ms. The compliance precheck dominates the latency budget. When human escalation is not triggered, Step 8 adds zero latency.

| Step | Operation | Target (ms) | Max (ms) |
|------|-----------|-------------|----------|
| 1 | Policy Resolution | 5 | 50 |
| 2 | Amount Validation | 1 | 5 |
| 3 | Daily Spend Calc | 15 | 100 |
| 4 | Monthly Spend Calc | 15 | 100 |
| 5 | Counterparty Validation | 5 | 30 |
| 6 | Category Validation | 2 | 10 |
| 7 | Wallet Balance Check | 10 | 50 |
| 8 | Human Escalation | 0 (skip) | 72h |
| 9 | Compliance Precheck | 100 | 500 |
| 10 | Record and Decision | 10 | 50 |
| | **Total (no escalation)** | **~163** | **~895** |

The 163ms target assumes warm caches and no lock contention. The 895ms max assumes cold caches, moderate contention on the advisory lock, and a slow compliance scan. In production, we see p50 at 170ms, p95 at 340ms, and p99 at 520ms. The p99 is almost always dominated by the compliance step.

---

## API Examples

### Successful Authorization

```bash
curl -X POST https://api.example.com/pulse-api/payments/request \
  -H "Content-Type: application/json" \
  -H "Authorization: PULSE-HMAC-SHA256 KeyId=key_001, Signature=a3f8..., Timestamp=2026-04-14T10:35:00Z" \
  -d '{
    "idempotency_key": "idk_unique_abc123",
    "sender_org_id": "org_x9y8z7",
    "receiver_org_id": "org_m3n4o5",
    "counterparty_id": "cp_xyz789",
    "amount": 5000.00,
    "currency": "USD",
    "category": "vendor_payment",
    "description": "Invoice #INV-2026-0412 payment",
    "metadata": {
      "invoice_id": "INV-2026-0412",
      "purchase_order": "PO-8837"
    }
  }'
```

Response (200 OK):

```json
{
  "authorization_id": "auth_def456",
  "payment_id": "pay_abc123",
  "decision": "approved",
  "reason_code": null,
  "amount": 5000.00,
  "currency": "USD",
  "authorized_at": "2026-04-14T10:35:25Z",
  "expires_at": "2026-04-14T11:35:25Z",
  "risk_score": 0.12,
  "compliance_result": "pass",
  "human_review_required": false
}
```

### Denied Authorization (Blocked Counterparty)

```bash
curl -X POST https://api.example.com/pulse-api/payments/request \
  -H "Content-Type: application/json" \
  -H "Authorization: PULSE-HMAC-SHA256 KeyId=key_001, Signature=b7c2..., Timestamp=2026-04-14T10:36:00Z" \
  -d '{
    "idempotency_key": "idk_unique_def456",
    "sender_org_id": "org_x9y8z7",
    "receiver_org_id": "org_m3n4o5",
    "counterparty_id": "cp_blocked_001",
    "amount": 2500.00,
    "currency": "USD",
    "category": "vendor_payment",
    "description": "Attempt against blocked counterparty"
  }'
```

Response (200 OK -- denials are not HTTP errors, they are business logic outcomes):

```json
{
  "authorization_id": "auth_ghi789",
  "payment_id": "pay_def456",
  "decision": "denied",
  "reason_code": "counterparty_blocked",
  "amount": 2500.00,
  "currency": "USD",
  "authorized_at": null,
  "expires_at": null,
  "risk_score": null,
  "compliance_result": null,
  "human_review_required": false
}
```

This is worth emphasizing: denials return HTTP 200. The HTTP status code reflects the health of the API call, not the business decision. A 200 with `"decision": "denied"` means the pipeline executed correctly and made a decision. A 500 means something went wrong with the pipeline itself. We learned this the hard way when an early integration partner's error-handling middleware intercepted our 403 denial responses and retried them in an infinite loop.

### Authorization Requiring Human Escalation

```bash
curl -X POST https://api.example.com/pulse-api/payments/request \
  -H "Content-Type: application/json" \
  -H "Authorization: PULSE-HMAC-SHA256 KeyId=key_001, Signature=c9d1..., Timestamp=2026-04-14T10:37:00Z" \
  -d '{
    "idempotency_key": "idk_unique_ghi789",
    "sender_org_id": "org_x9y8z7",
    "receiver_org_id": "org_m3n4o5",
    "counterparty_id": "cp_approved_001",
    "amount": 15000.00,
    "currency": "USD",
    "category": "vendor_payment",
    "description": "Large vendor payment requiring review"
  }'
```

Response (202 Accepted -- pending human review):

```json
{
  "authorization_id": "auth_jkl012",
  "payment_id": "pay_ghi789",
  "decision": "pending_human_review",
  "reason_code": null,
  "amount": 15000.00,
  "currency": "USD",
  "authorized_at": null,
  "expires_at": null,
  "risk_score": 0.72,
  "compliance_result": "pass",
  "human_review_required": true,
  "escalation_reason": "amount_exceeds_threshold",
  "escalation_timeout_at": "2026-04-17T10:37:00Z"
}
```

The client should poll for the decision:

```bash
curl -X GET "https://api.example.com/pulse-api/payments/status?payment_id=pay_ghi789" \
  -H "Authorization: PULSE-HMAC-SHA256 KeyId=key_001, Signature=d2e3..., Timestamp=2026-04-14T10:38:00Z"
```

### Checking Authorization Status

```bash
curl -X GET "https://api.example.com/pulse-api/payments/authorization?authorization_id=auth_def456" \
  -H "Authorization: PULSE-HMAC-SHA256 KeyId=key_001, Signature=e4f5..., Timestamp=2026-04-14T10:39:00Z"
```

Response (200 OK):

```json
{
  "authorization_id": "auth_def456",
  "payment_id": "pay_abc123",
  "decision": "approved",
  "reason_code": null,
  "amount": 5000.00,
  "currency": "USD",
  "authorized_at": "2026-04-14T10:35:25Z",
  "expires_at": "2026-04-14T11:35:25Z",
  "is_expired": false,
  "is_executed": false
}
```

---

## Deadlock Handling

Advisory locks do not deadlock in the traditional sense because they are single-resource locks (one agent-org pair). However, when the wallet balance check in Step 7 acquires a separate lock on the org wallet, there is a theoretical deadlock window: Transaction A holds the agent-org spend lock and waits for the org wallet lock, while Transaction B (from a different agent in the same org) holds the org wallet lock and waits for a different agent-org spend lock. In practice, this is vanishingly unlikely because the spend lock is held for 15-40ms and the wallet lock acquisition timeout is 100ms.

If a lock acquisition times out, we do not retry within the pipeline. We abort the pipeline and return a transient error to the gateway. The gateway's own retry logic (one automatic retry with a 500ms delay) handles it. We chose this over in-pipeline retry because a lock timeout usually indicates genuine contention, and retrying immediately would just queue behind the same contention.

We log every lock timeout with the payment ID, the lock key, the hold duration of the blocking transaction (if available), and the wall-clock time. This gives us enough data to diagnose contention patterns without adding monitoring overhead to the hot path.

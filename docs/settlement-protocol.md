# Settlement Protocol

Version: 2.0.0
Status: Production
Last Updated: 2026-04-14

---

## Why Three Settlement Modes Exist Instead of One

We started with instant-only. Every authorized payment immediately debited the sender wallet, credited the receiver wallet, and wrote the audit record in a single atomic transaction. Clean, simple, fast. It worked beautifully for intra-platform payments where both parties were known, trusted, and operating in good faith.

Then a cross-org data purchase went wrong. The buyer paid, the seller's agent crashed mid-delivery, and there was no mechanism to recover the funds without manual intervention. The buyer's wallet was debited. The seller's wallet was credited. The data was never delivered. We opened a support ticket, manually reversed the transaction, notified both parties, and spent three days untangling the audit trail because the reversal did not fit any of our existing event types.

That is when escrow became non-optional. We needed a way to hold funds in a neutral position -- not in the sender's wallet, not in the receiver's -- until the exchange was verifiably complete. The escrow mode was built in the two weeks following that incident.

External settlement came third, driven by a different pain point. Organizations needed to pay vendors and contractors who did not have platform wallets. Funds had to leave the platform entirely and settle through bank transfers, wire transfers, or card networks. We could have told organizations to handle external payments outside the platform, but that would break the audit trail. Every payment that leaves the platform's visibility is a gap in the compliance record. So we built the external rail adapter system to keep external payments within the same authorization, settlement, and auditing pipeline as everything else.

Three modes, three origin stories. Each one exists because a real scenario forced it.

---

## Instant Settlement

Instant settlement is the default mode for intra-platform payments where both parties have wallets on the platform. The entire operation -- debit, credit, status update, event recording -- executes as a single atomic database transaction. Either everything succeeds or nothing does. There is no partial state.

We chose serializable transaction isolation for settlement, which is heavier than the read-committed isolation most applications use. The performance cost is real: serializable transactions hold wider locks and are more likely to abort under contention. We accepted this cost because settlement is the point of no return. An authorization can be voided. A settlement cannot (without a separate refund flow). The correctness requirements at settlement time justify the performance overhead.

### The Atomic Flow

```
Step 1:  BEGIN transaction (SERIALIZABLE isolation)
Step 2:  Debit sender wallet
         -- Verify balance >= amount; overdraft is a hard failure
Step 3:  Credit receiver wallet
Step 4:  Update payment status to settled with timestamp
Step 5:  Record settlement event with before/after balances for both parties
Step 6:  COMMIT transaction
         -- If any step fails, the entire transaction rolls back
         -- The payment returns to authorized status as if settlement was never attempted
```

After the transaction commits, we fire a sequence of post-commit actions. These are not part of the atomic transaction because they involve external systems (webhook endpoints, inter-agent messaging) that cannot participate in our database transaction. If a webhook delivery fails, the settlement is still committed. Webhooks are notifications, not confirmations.

```
Step 7:  Dispatch webhook to sender org
Step 8:  Dispatch webhook to receiver org
Step 9:  Send settlement_complete message to sender org agents (route OS-10)
Step 10: Send settlement_complete message to receiver org agents (route OS-10)
Step 11: Send settlement_event to the Payment Auditor (route PR-05)
```

### Transaction Hashes

Every settlement event includes a `transaction_hash` computed over the payment ID, sender org, receiver org, amount, currency, and settlement timestamp. The Payment Auditor recomputes this hash independently and compares it against the stored value. Any mismatch triggers an immediate tamper alert that escalates to human investigation.

```
hash_input = payment_id + "|" + sender_org_id + "|" + receiver_org_id
           + "|" + amount + "|" + currency + "|" + settled_at
transaction_hash = "sha256:" + SHA256(hash_input)
```

We considered using a Merkle tree over all settlement events within a time window (so that any tampering would invalidate the root hash and be detectable). We decided against it because the Merkle approach makes it hard to pinpoint which specific event was tampered with -- you know something changed but not what. Our per-event hash approach lets the Auditor identify the exact tampered record immediately.

### Settlement Event Schema

```json
{
  "event_id": "evt_set_001",
  "payment_id": "pay_abc123",
  "authorization_id": "auth_def456",
  "settlement_mode": "instant",
  "sender_org_id": "org_x9y8z7",
  "receiver_org_id": "org_m3n4o5",
  "amount": 5000.00,
  "currency": "USD",
  "sender_balance_before": 75000.00,
  "sender_balance_after": 70000.00,
  "receiver_balance_before": 30000.00,
  "receiver_balance_after": 35000.00,
  "settled_at": "2026-04-14T10:35:30Z",
  "transaction_hash": "sha256:a3f8b2c1d4e5f6..."
}
```

---

## Escrow Settlement

Escrow settlement holds funds in a platform-managed escrow wallet until a release condition is met, a dispute is filed, or the escrow period expires. We built this mode because instant settlement assumes both parties fulfill their obligations simultaneously. In reality, many agent-to-agent transactions involve asynchronous fulfillment: one party pays, the other delivers later.

### The States and Why Each Exists

```
              +--------+
              |  hold  |
              +--------+
             /    |     \
            v     v      v
     +--------+ +--------+ +--------+
     |released| |expired | |disputed|
     +--------+ +--------+ +--------+
                                |
                                v
                          +-----------+
                          | resolved  |
                          +-----------+
```

**Hold**: Funds have been debited from the sender and placed in the escrow wallet. Neither party can access them. This state persists until someone takes an action (release, dispute) or the clock runs out (expiry).

**Released**: The authorized releaser confirmed that obligations were met and released the funds to the receiver. This is the happy path.

**Expired**: Nobody released the funds and nobody disputed within the configured window. The funds return to the sender automatically. We debated whether expiry should be automatic or require human intervention. We chose automatic because a stale escrow sitting in `hold` indefinitely is worse for both parties than an automatic return. The sender gets their money back; the receiver can renegotiate if needed.

**Disputed**: One party filed a dispute. Funds are frozen -- no release, no expiry -- until a human mediator resolves it.

**Resolved**: The mediator issued a decision: full release to receiver, full return to sender, or a split. The resolved state is terminal.

### ESC-RACE-001: Concurrent Release and Dispute

This was our first escrow-specific race condition. A release request and a dispute request arrive within milliseconds of each other. The release handler reads the escrow state as `hold`, validates the releaser's authority, and begins the release transaction. Meanwhile, the dispute handler also reads the state as `hold`, validates the dispute, and begins the dispute transaction. If both transactions commit, the funds are simultaneously released to the receiver and frozen for dispute resolution, which is an impossible state.

We prevent ESC-RACE-001 with an exclusive lock on the escrow record. Both the release handler and the dispute handler must acquire this lock before reading the escrow state. The first one to acquire the lock proceeds; the second one reads the updated state (no longer `hold`) and rejects with `invalid_escrow_state`.

```
-- Pseudocode for both release and dispute handlers
ACQUIRE exclusive_lock(escrow_id)
    current_state = READ escrow_state WHERE escrow_id = target_escrow
    IF current_state != hold THEN
        RELEASE exclusive_lock(escrow_id)
        REJECT with invalid_escrow_state
    END IF
    -- proceed with release or dispute logic
    UPDATE escrow_state = new_state
RELEASE exclusive_lock(escrow_id)
```

### ESC-RACE-002: Expiry During Release

The second escrow race condition is subtler. The escrow expiry scheduler fires at the exact moment an authorized user submits a release. The scheduler reads the state as `hold` and begins returning funds to the sender. The release handler reads the state as `hold` and begins releasing funds to the receiver. Both transactions try to debit the escrow wallet. One of them will fail on the wallet debit (insufficient balance because the other transaction already drained it), but only if the database serialization catches the conflict.

We handle ESC-RACE-002 the same way as ESC-RACE-001: the exclusive lock on the escrow record. The scheduler acquires the lock before checking the state. If a release is in progress, the scheduler waits for the lock, then reads the state as `released` (not `hold`), and skips the expiry. If the scheduler gets the lock first, the release handler reads the state as `expired` and rejects.

An earlier implementation tried to handle this with optimistic locking on the escrow state (check the state version before committing). It worked 99.9% of the time, but the 0.1% failure mode was catastrophic: both transactions committed against a stale state version, resulting in a double-debit of the escrow wallet. We switched to exclusive locks after that incident.

### Escrow Hold Flow

```bash
curl -X POST https://api.example.com/pulse-api/payments/escrow/hold \
  -H "Content-Type: application/json" \
  -H "Authorization: PULSE-HMAC-SHA256 KeyId=key_001, Signature=f6a7..., Timestamp=2026-04-14T11:00:00Z" \
  -d '{
    "payment_id": "pay_abc123",
    "authorization_id": "auth_def456",
    "escrow_duration_hours": 168,
    "release_conditions": {
      "type": "manual",
      "authorized_releasers": ["user_human_001", "user_human_002"]
    }
  }'
```

The flow internally:

```
Step 1:  Receive escrow hold request
Step 2:  BEGIN transaction (SERIALIZABLE)
Step 3:  Debit sender wallet (balance must be sufficient)
Step 4:  Credit escrow wallet for this specific payment
Step 5:  Update payment status to escrow_hold with hold and expiry timestamps
Step 6:  Record escrow event (action: hold)
Step 7:  COMMIT transaction
Step 8:  Dispatch webhooks to both organizations (escrow.hold event)
Step 9:  Send settlement_event to Payment Auditor (route PR-05)
```

### Escrow Release Flow

```bash
curl -X POST https://api.example.com/pulse-api/payments/escrow/release \
  -H "Content-Type: application/json" \
  -H "Authorization: PULSE-HMAC-SHA256 KeyId=key_001, Signature=g8b9..., Timestamp=2026-04-14T12:00:00Z" \
  -d '{
    "payment_id": "pay_abc123",
    "released_by": "user_human_001",
    "release_note": "Deliverables verified and accepted"
  }'
```

Internally:

```
Step 1:  ACQUIRE exclusive_lock(escrow_id)
Step 2:  Validate released_by is in authorized_releasers list
Step 3:  Validate escrow state is hold
Step 4:  BEGIN transaction (SERIALIZABLE)
Step 5:  Debit escrow wallet
Step 6:  Credit receiver wallet
Step 7:  Update payment status to settled
Step 8:  Record escrow event (action: release) and settlement event
Step 9:  COMMIT transaction
Step 10: RELEASE exclusive_lock(escrow_id)
Step 11: Dispatch webhooks (escrow.released event)
Step 12: Send settlement_event to Payment Auditor (route PR-05)
```

### Escrow Expiry Flow

The scheduler subsystem monitors all escrow holds and fires expiry when the configured duration elapses without a release or dispute.

```
Step 1:  Scheduler detects escrow_expires_at <= NOW() for a payment in hold state
Step 2:  ACQUIRE exclusive_lock(escrow_id)
Step 3:  Re-read escrow state (may have changed since scheduler pickup)
         IF state != hold THEN skip -- already released or disputed
Step 4:  BEGIN transaction (SERIALIZABLE)
Step 5:  Debit escrow wallet
Step 6:  Credit sender wallet (return funds)
Step 7:  Update payment status to escrow_expired
Step 8:  Record escrow event (action: expire)
Step 9:  COMMIT transaction
Step 10: RELEASE exclusive_lock(escrow_id)
Step 11: Dispatch webhooks (escrow.expired event)
Step 12: Send settlement_event to Payment Auditor
```

### Escrow Dispute Flow

Either party can file a dispute while the escrow is in `hold` state. Disputes freeze the escrow -- no release and no expiry can proceed while a dispute is active.

```bash
curl -X POST https://api.example.com/pulse-api/payments/escrow/dispute \
  -H "Content-Type: application/json" \
  -H "Authorization: PULSE-HMAC-SHA256 KeyId=key_001, Signature=h1c2..., Timestamp=2026-04-14T14:00:00Z" \
  -d '{
    "payment_id": "pay_abc123",
    "disputed_by_org_id": "org_m3n4o5",
    "dispute_reason": "Deliverables not received as specified",
    "evidence_references": ["doc_001", "doc_002"]
  }'
```

Internally:

```
Step 1:  ACQUIRE exclusive_lock(escrow_id)
Step 2:  Validate escrow state is hold
Step 3:  BEGIN transaction
Step 4:  Update payment status to escrow_disputed
Step 5:  Freeze escrow (prevents release and expiry)
Step 6:  Record escrow event (action: dispute)
Step 7:  COMMIT transaction
Step 8:  RELEASE exclusive_lock(escrow_id)
Step 9:  Dispatch webhooks (escrow.disputed event)
Step 10: Send escalation_required to Property Dispatcher (route PR-13)
Step 11: Human mediator assigned, reviews evidence, communicates with both parties
Step 12: Mediator issues resolution:
         - release_to_receiver: full release to receiver
         - return_to_sender: full return to sender
         - split: partial credit to both parties in a single transaction
```

---

## External Settlement

External settlement handles payments that must leave the platform and settle through bank transfers, wire transfers, card networks, or other third-party processors. The challenge here is maintaining the audit trail across a boundary we do not control.

The key design decision: we debit the sender wallet immediately and park the funds in a transit wallet. The transit wallet is a platform-managed holding area, distinct from escrow. Escrow is for intra-platform holds with dispute resolution. Transit is for funds in flight to external systems. We keep them separate because they have different lifecycle rules: escrow has authorized releasers and dispute flows, transit has polling intervals and external reference tracking.

### External Settlement Flow

```
Step 1:  Receive execute_payment with settlement_mode = external
Step 2:  BEGIN transaction (SERIALIZABLE)
Step 3:  Debit sender wallet
Step 4:  Credit transit wallet
Step 5:  Update payment status to executing_external
Step 6:  COMMIT transaction
Step 7:  Submit payment instruction to external rail adapter
         -- Adapter selection based on destination country, currency,
         -- amount thresholds, and speed preference
Step 8:  External rail returns a tracking reference
Step 9:  Store tracking reference in payment record
Step 10: Update payment status to pending_external
Step 11: Background poller checks external rail status:
         -- Every 60 seconds for the first hour
         -- Every 5 minutes for up to 5 business days
Step 12: On external confirmation:
         -- Debit transit wallet
         -- Update payment status to settled
         -- Record settlement event
         -- Dispatch webhooks
Step 13: On external failure:
         -- Debit transit wallet
         -- Credit sender wallet (return funds)
         -- Update payment status to external_failed
         -- Dispatch failure webhooks
```

### External Rail Adapters

The platform uses a pluggable adapter system. Each adapter implements a standard interface:

```
interface ExternalRailAdapter:
    submit(instruction) -> tracking_reference
    status(reference) -> rail_status
    cancel(reference) -> cancel_result
    supported_currencies() -> list of currency codes
    supported_countries() -> list of country codes
    estimated_settlement_time() -> duration
```

Adapter selection is deterministic based on a priority-ordered routing table configured per organization. If the first-priority adapter rejects the instruction (unsupported currency, amount outside its range), the system falls through to the second-priority adapter, and so on. If no adapter accepts the instruction, the payment fails with `no_eligible_rail`.

---

## Why Not Blockchain

This question comes up enough that it warrants a direct answer.

Blockchain technology offers two properties that sound ideal for a settlement system: immutability and distributed consensus. A settlement recorded on a blockchain cannot be altered, and all participants agree on the state without trusting a central authority. We evaluated several blockchain-based settlement architectures early in the design process and rejected them for five specific reasons.

**Finality takes seconds to minutes, not milliseconds.** Our instant settlement target is 200ms. Even the fastest production blockchains have block times measured in seconds and practical finality times measured in minutes (accounting for the recommended number of confirmation blocks). For a payment system where agents are making programmatic decisions in real time, settlement latency measured in minutes is disqualifying. An agent that authorized a purchase at 10:00:00 should not be waiting until 10:02:30 to confirm the funds moved.

**Smart contract bugs are irreversible.** When we find a bug in our settlement logic, we fix it, deploy the fix, and if necessary, manually correct the affected records under audit supervision. When a smart contract has a bug, the bug is the contract. Immutability -- the feature -- becomes the problem. The history of smart contract exploits is long and expensive. We do not want our settlement system's correctness to depend on getting the code right the first time with no ability to patch.

**Gas fees on micro-transactions are irrational.** Agent-to-agent payments include frequent small transactions: $5 data lookups, $12 API calls, $0.50 notification dispatches. Paying a gas fee on each of these -- even on a low-fee chain -- adds cost that scales with transaction volume, not transaction value. Our database transaction cost is effectively zero marginal cost per settlement. We process thousands of micro-settlements per hour without the gas fee overhead eating into the economics.

**Regulatory frameworks do not recognize on-chain escrow.** Our escrow mode exists within a legal framework where disputes are resolved by human mediators and funds are held in accounts that comply with money transmission regulations. On-chain escrow (funds locked in a smart contract) exists in a regulatory gray area. Most financial regulators have not issued clear guidance on whether smart contract escrow satisfies the legal requirements for held funds. We cannot build a compliance-dependent system on an unresolved regulatory question.

**Compliance requires mutable policy enforcement.** When a sanctions list is updated, we need to immediately freeze payments involving newly sanctioned entities. This requires the ability to mutate policy state and have that mutation take immediate effect on in-flight transactions. Blockchain-based systems with immutable smart contracts cannot retroactively apply new compliance rules to pending transactions without complex upgrade proxy patterns that introduce their own vulnerabilities.

What we use instead: ACID transactions with append-only audit logs. We get the same integrity guarantees -- every settlement is atomic, every event is recorded immutably in an append-only log, every record has a tamper-evident hash -- but faster, cheaper, and within legal frameworks that regulators understand. The append-only audit log gives us effective immutability (records are never updated, only appended) without the overhead of distributed consensus. The Payment Auditor independently verifies every settlement hash, providing the same verification function that a blockchain validator would, but in milliseconds rather than seconds.

---

## Retry Logic

All settlement operations use the same retry policy when a transient failure occurs. Transient failures include database timeouts, network partitions, and external rail temporary unavailability. Non-transient failures (insufficient balance, frozen wallet, expired authorization) are never retried.

### Retry Parameters

Maximum attempts: 3 (including the initial attempt). Backoff is exponential with base 2 seconds. Jitter of +/- 500ms is applied to each delay to prevent thundering herd effects when multiple payments fail simultaneously.

| Attempt | Delay | Cumulative Wait |
|---------|-------|-----------------|
| 1 | 0s (immediate) | 0s |
| 2 | ~2s (+/- 500ms jitter) | ~2s |
| 3 | ~4s (+/- 500ms jitter) | ~6s |

After 3 failed attempts, the payment is marked as failed. The Payment Auditor is notified. Failure webhooks are dispatched to both organizations.

### Non-Retryable Errors

These errors cause immediate failure without consuming retry attempts:

- `insufficient_balance` -- The wallet balance is genuinely insufficient, not a transient read failure.
- `wallet_frozen` -- The sender or receiver wallet is administratively frozen.
- `payment_already_settled` -- A duplicate settlement attempt (should not happen with idempotency, but we defend against it).
- `authorization_expired` -- The authorization window has elapsed. The payment must be re-authorized.
- `invalid_payment_state` -- The payment is not in a state that allows settlement (e.g., already refunded).

### Retry Flow (Pseudocode)

```
attempt = 1
max_attempts = 3
base_delay = 2

WHILE attempt <= max_attempts DO
    result = execute_settlement(payment)

    IF result.success THEN
        RETURN result
    END IF

    LOG retry_event(payment_id, attempt, result.error_code, NOW())

    IF attempt = max_attempts THEN
        MARK payment as failed
        NOTIFY auditor(payment_id, settlement_failed, max_attempts, result.error_code)
        DISPATCH failure_webhooks(sender_org, receiver_org, payment)
        RETURN failure_result
    END IF

    delay = base_delay * POWER(2, attempt - 1)
    jitter = random(-500, 500) / 1000.0
    SLEEP(delay + jitter)

    attempt = attempt + 1
END WHILE
```

### The WEBHOOK-RETRY-001 Bug

This is worth documenting because it was a subtle interaction between the settlement retry logic and the webhook delivery system that caused duplicate notifications.

The bug: when a settlement attempt failed and was retried, the retry logic correctly re-executed the settlement transaction. But the post-commit webhook dispatch from the failed attempt had already been enqueued. The webhook dispatcher operates asynchronously -- it picks up dispatch requests from a queue and delivers them independently of the settlement transaction. When the first settlement attempt failed and rolled back, the webhook dispatch request was *not* rolled back because it had already been written to the webhook queue (which is a separate data store from the settlement database).

So the first attempt fails, enqueues a webhook, rolls back the settlement. The second attempt succeeds, enqueues another webhook, commits the settlement. The webhook dispatcher delivers both: a `settlement.failed` webhook (from the first attempt's enqueue) and a `settlement.completed` webhook (from the second attempt). The receiver sees a failure followed by a success, which is technically accurate in sequence but confusing. Worse: some receivers' automated systems processed the failure webhook and triggered a refund request before the success webhook arrived.

The fix was straightforward but required a design change. We moved webhook enqueuing inside the settlement transaction. If the transaction rolls back, the webhook enqueue rolls back with it. If the transaction commits, the webhook is guaranteed to be enqueued. This means webhooks now share the settlement database's write path, which marginally increases settlement transaction duration (by about 2ms for the queue write), but eliminates phantom webhooks from failed attempts.

We also added the `X-Pulse-Delivery-Id` header to all webhooks specifically because of this bug. Even after the fix, we wanted receivers to have a deduplication mechanism in case of any future edge cases. The delivery ID is unique per logical event, and retried deliveries of the same event reuse the same delivery ID.

### Retry Logging

Every retry attempt is logged with full context:

```json
{
  "retry_log_id": "rtl_001",
  "payment_id": "pay_abc123",
  "attempt_number": 2,
  "error_code": "db_timeout",
  "error_message": "Transaction exceeded 5000ms timeout",
  "attempted_at": "2026-04-14T10:35:32Z",
  "next_retry_at": "2026-04-14T10:35:36Z"
}
```

---

## Webhook Security

Settlement webhooks notify organizations of payment events. Every webhook is signed, every delivery is logged, and every failure is tracked.

### Signature Computation

Every webhook includes an `X-Pulse-Signature` header with an HMAC-SHA256 signature computed over the raw request body using the organization's webhook secret. The signature covers the exact bytes of the JSON body -- no whitespace normalization, no field reordering. This is critical because HMAC is byte-sensitive; normalizing the JSON before signing would require both sides to agree on a normalization algorithm, which is a common source of signature verification bugs.

```
signature_input = raw_request_body (UTF-8 encoded JSON, exact bytes as sent)
signature = HMAC-SHA256(org_webhook_secret, signature_input)
header_value = "sha256=" + hex_encode(signature)
```

### Webhook Format

```
POST {org.webhook_url}
Content-Type: application/json
X-Pulse-Signature: sha256=a3f8b2c1d4e5...
X-Pulse-Event: settlement.completed
X-Pulse-Delivery-Id: dlv_unique_001
X-Pulse-Timestamp: 2026-04-14T10:35:31Z

{
  "event": "settlement.completed",
  "delivery_id": "dlv_unique_001",
  "timestamp": "2026-04-14T10:35:31Z",
  "payload": {
    "payment_id": "pay_abc123",
    "settlement_mode": "instant",
    "amount": 5000.00,
    "currency": "USD",
    "sender_org_id": "org_x9y8z7",
    "receiver_org_id": "org_m3n4o5",
    "settled_at": "2026-04-14T10:35:30Z",
    "transaction_hash": "sha256:a3f8b2c1d4e5f6..."
  }
}
```

### Event Types

| Event | When It Fires |
|-------|--------------|
| `settlement.completed` | Instant settlement committed |
| `settlement.failed` | Settlement failed after all retry attempts |
| `escrow.hold` | Funds placed in escrow |
| `escrow.released` | Escrow released to receiver |
| `escrow.expired` | Escrow expired, funds returned to sender |
| `escrow.disputed` | Dispute filed on escrowed payment |
| `escrow.resolved` | Dispute resolved by mediator |
| `external.submitted` | Payment submitted to external rail |
| `external.settled` | External rail confirmed settlement |
| `external.failed` | External rail reported failure |
| `refund.completed` | Refund processed |
| `authorization.expired` | Authorization expired without execution |

### Webhook Delivery Retry

When a delivery fails (non-2xx response or network error), we retry with escalating backoff:

| Attempt | Delay After Failure | Total Elapsed |
|---------|-------------------- |---------------|
| 1 | Immediate | 0 |
| 2 | 30 seconds | 30s |
| 3 | 2 minutes | 2.5m |
| 4 | 8 minutes | 10.5m |
| 5 | 30 minutes | 40.5m |
| 6 | 1 hour | 1h 40m |
| 7 | 2 hours | 3h 40m |
| 8 | 4 hours | 7h 40m |
| 9 | 8 hours | 15h 40m |
| 10 | 16 hours | 31h 40m |

Each attempt is logged with the HTTP status (or network error) and the response body truncated to 1024 bytes.

### Automatic Webhook Disabling

After 10 consecutive delivery failures across any combination of events, the webhook endpoint is disabled. When this happens:

1. The org admin gets a dashboard notification with the failure details.
2. All pending deliveries for that endpoint move to a dead-letter queue retained for 30 days.
3. The admin must re-enable the webhook manually via `POST /pulse-api/payments/webhook/register`.
4. On re-enable, the platform replays dead-letter events in chronological order with normal retry policy.

We chose 10 consecutive failures (not 10 total) as the threshold because intermittent failures are normal -- network blips, deployment windows, brief outages. Only sustained failure indicates a genuinely broken endpoint that should stop receiving traffic.

---

## Auditor Confirmation Flow

After every settlement event, the Payment Executor sends a `settlement_event` message to the Payment Auditor via route PR-05. The Auditor is a separate agent with read-only access to settlement records. It cannot modify settlements; it can only verify them and raise alerts.

### Verification Steps

```
Step 1:  Receive settlement_event message
Step 2:  Recompute transaction_hash from event fields
         IF computed_hash != stored_hash THEN
             RAISE tamper_alert (immediate escalation)
         END IF
Step 3:  Verify sender_balance_after = sender_balance_before - amount
Step 4:  Verify receiver_balance_after = receiver_balance_before + amount
Step 5:  Verify payment status transition is valid
         (authorized -> executing -> settled is the only valid path)
Step 6:  Write immutable audit record
Step 7:  Send audit_confirmation back to Executor (route PR-06)
```

If any verification fails, the Auditor sends an alert (route OS-06) to the Metrics Collector, which escalates to a human investigator via the Property Dispatcher. The affected payment is flagged as `audit_flagged` and cannot participate in any subsequent settlement or refund until a human clears the flag.

---

## Refund Settlement

Refunds reverse a previously settled payment. The flow mirrors instant settlement but with reversed debit/credit operations.

```bash
curl -X POST https://api.example.com/pulse-api/payments/refund \
  -H "Content-Type: application/json" \
  -H "Authorization: PULSE-HMAC-SHA256 KeyId=key_001, Signature=i2d3..., Timestamp=2026-04-14T15:00:00Z" \
  -d '{
    "original_payment_id": "pay_abc123",
    "refund_amount": 5000.00,
    "reason": "Service not rendered"
  }'
```

Refund flow:

```
Step 1:  Validate original payment exists and is in settled state
Step 2:  Validate refund_amount <= original_payment.amount
         (partial refunds are permitted)
Step 3:  BEGIN transaction (SERIALIZABLE)
Step 4:  Debit receiver wallet (original receiver pays back)
Step 5:  Credit sender wallet (original sender receives refund)
Step 6:  Create refund payment record linked to the original
Step 7:  Update original payment's refund tracking
Step 8:  Record settlement event for the refund
Step 9:  COMMIT transaction
Step 10: Dispatch webhooks (refund.completed event)
Step 11: Send settlement_event to Auditor
```

Partial refunds are tracked cumulatively. The sum of all refunds against an original payment cannot exceed the original payment amount. We enforce this within the transaction to prevent concurrent partial refund requests from exceeding the original amount (the same TOCTOU pattern from the authorization protocol).

---

## Settlement Timing and SLAs

| Mode | Target Latency | Maximum Latency | Availability SLA |
|------|---------------|-----------------|------------------|
| Instant | 200ms | 2s | 99.95% |
| Escrow Hold | 300ms | 3s | 99.95% |
| Escrow Release | 300ms | 3s | 99.95% |
| External | Varies by rail | 5 business days | 99.9% |
| Refund | 200ms | 2s | 99.95% |

The external settlement SLA is lower (99.9% vs 99.95%) because it depends on third-party rail availability that we do not control. The 5 business day maximum accounts for the slowest bank transfer corridors we support.

---

## Settlement State Machine

Every payment's lifecycle through the settlement layer follows this state machine. Every transition is recorded in an append-only state transition log with the previous state, new state, timestamp, and the agent that triggered the transition.

```
  authorized
      |
      v
  executing ---------> failed  (non-retryable error or retries exhausted)
      |
      +------> settled  (instant mode)
      |
      +------> escrow_hold ------> escrow_released ----> settled
      |              |
      |              +-----------> escrow_expired
      |              |
      |              +-----------> escrow_disputed ----> escrow_resolved
      |
      +------> executing_external --> pending_external --> settled
                                          |
                                          +-------------> external_failed
```

The state transition log is the authoritative history of every payment. When a discrepancy is found between the payment's current status and its expected status, the transition log is the source of truth. It tells us not just where the payment is, but how it got there and who moved it at every step.

---

## Settlement Receipt

After settlement completes, a receipt is available:

```bash
curl -X GET "https://api.example.com/pulse-api/payments/receipt?payment_id=pay_abc123" \
  -H "Authorization: PULSE-HMAC-SHA256 KeyId=key_001, Signature=j3e4..., Timestamp=2026-04-14T16:00:00Z"
```

```json
{
  "receipt_id": "rct_001",
  "payment_id": "pay_abc123",
  "authorization_id": "auth_def456",
  "settlement_mode": "instant",
  "sender_org_id": "org_x9y8z7",
  "sender_org_name": "PortCo Alpha",
  "receiver_org_id": "org_m3n4o5",
  "receiver_org_name": "PortCo Beta",
  "amount": 5000.00,
  "currency": "USD",
  "category": "vendor_payment",
  "description": "Invoice #INV-2026-0412 payment",
  "authorized_at": "2026-04-14T10:35:25Z",
  "settled_at": "2026-04-14T10:35:30Z",
  "transaction_hash": "sha256:a3f8b2c1d4e5f6...",
  "audit_confirmation_id": "auc_001",
  "audit_confirmed_at": "2026-04-14T10:35:31Z"
}
```

The receipt is immutable once generated. It includes the audit confirmation ID, proving that the Payment Auditor verified the settlement's integrity. Organizations use these receipts for their own bookkeeping, tax reporting, and compliance documentation.

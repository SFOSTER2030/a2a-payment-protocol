# A2A Payment Protocol — Events Specification

## Webhook Events

The Pulse AI payment platform delivers webhook events via HTTPS POST to registered endpoints. All events are signed with HMAC-SHA256 using the endpoint's shared secret.

### Delivery Guarantees

- **At-least-once delivery**: Events may be delivered more than once. Use `event_id` for deduplication.
- **Ordering**: Events include a monotonically increasing `sequence_number` per agent. Consumers should reorder if events arrive out of sequence.
- **Retry behavior**: Failed deliveries (non-2xx response or timeout) are retried with exponential backoff: 30s, 2m, 10m, 1h, 6h, 24h (6 attempts total). After exhaustion, the event is moved to the dead-letter queue and the endpoint `failure_count` is incremented.
- **Timeout**: Endpoints must respond within 10 seconds or the delivery is marked as failed.
- **Idempotency**: Every event carries a unique `event_id` (UUID v4). Consumers must store processed event IDs and skip duplicates.

---

### 1. `payment.requested`

Fired when a new payment request is submitted.

**Trigger condition**: A call to `POST /pulse-api/v1/payments/request` succeeds.

```json
{
  "event_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "event_type": "payment.requested",
  "sequence_number": 1001,
  "timestamp": "2026-04-14T12:00:00.000Z",
  "payload": {
    "payment_request_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "amount": 150.00,
    "currency": "USD",
    "sender_agent_id": "11111111-1111-1111-1111-111111111111",
    "receiver_agent_id": "22222222-2222-2222-2222-222222222222",
    "description": "Data processing service fee",
    "idempotency_key": "c9bf9e57-1685-4c89-bafb-ff5af830be8a"
  }
}
```

---

### 2. `payment.authorized`

Fired when a payment passes the authorization pipeline.

**Trigger condition**: The authorization pipeline returns `approved` status.

```json
{
  "event_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "event_type": "payment.authorized",
  "sequence_number": 1002,
  "timestamp": "2026-04-14T12:00:01.200Z",
  "payload": {
    "authorization_id": "d4e5f6a7-b8c9-0123-def4-567890abcdef",
    "payment_request_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "transaction_id": "e5f6a7b8-c9d0-1234-ef56-7890abcdef01",
    "risk_score": 12.5,
    "policy_checks_passed": 10,
    "policy_checks_total": 10,
    "authorized_by": "TransactionAuthorizer-Agent43"
  }
}
```

---

### 3. `payment.denied`

Fired when a payment is rejected by the authorization pipeline.

**Trigger condition**: Any policy check in the authorization pipeline fails with a hard deny.

```json
{
  "event_id": "c3d4e5f6-a7b8-9012-cdef-234567890abc",
  "event_type": "payment.denied",
  "sequence_number": 1003,
  "timestamp": "2026-04-14T12:00:01.500Z",
  "payload": {
    "authorization_id": "a1b2c3d4-5678-9abc-def0-123456789abc",
    "payment_request_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "reason_code": "POLICY_EXCEEDED_DAILY_LIMIT",
    "reason_message": "Daily spending limit of $500.00 exceeded for sender agent",
    "risk_score": 78.3,
    "failed_checks": [
      {
        "check_name": "daily_spend_limit",
        "reason": "Current daily spend $420.00 + $150.00 exceeds limit $500.00"
      }
    ]
  }
}
```

---

### 4. `payment.settled`

Fired when funds are successfully transferred between agent wallets.

**Trigger condition**: Settlement executor confirms the fund transfer is complete.

```json
{
  "event_id": "d4e5f6a7-b8c9-0123-defa-bcdef1234567",
  "event_type": "payment.settled",
  "sequence_number": 1004,
  "timestamp": "2026-04-14T12:00:02.800Z",
  "payload": {
    "transaction_id": "e5f6a7b8-c9d0-1234-ef56-7890abcdef01",
    "payment_request_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "amount": 150.00,
    "currency": "USD",
    "sender_agent_id": "11111111-1111-1111-1111-111111111111",
    "receiver_agent_id": "22222222-2222-2222-2222-222222222222",
    "settlement_reference": "STL-20260414-0001",
    "sender_new_balance": 350.00,
    "receiver_new_balance": 1150.00
  }
}
```

---

### 5. `payment.failed`

Fired when settlement fails after authorization.

**Trigger condition**: Settlement executor encounters an unrecoverable error (insufficient funds post-auth, system failure).

```json
{
  "event_id": "e5f6a7b8-c9d0-1234-efab-cdef12345678",
  "event_type": "payment.failed",
  "sequence_number": 1005,
  "timestamp": "2026-04-14T12:00:03.100Z",
  "payload": {
    "transaction_id": "e5f6a7b8-c9d0-1234-ef56-7890abcdef01",
    "payment_request_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "failure_reason": "INSUFFICIENT_FUNDS_POST_AUTH",
    "failure_message": "Sender wallet balance changed between authorization and settlement",
    "amount": 150.00,
    "currency": "USD",
    "retry_eligible": false
  }
}
```

---

### 6. `escrow.held`

Fired when funds are successfully placed in escrow.

**Trigger condition**: A call to `POST /pulse-api/v1/payments/escrow` succeeds and funds are locked.

```json
{
  "event_id": "f6a7b8c9-d0e1-2345-fabc-def123456789",
  "event_type": "escrow.held",
  "sequence_number": 1006,
  "timestamp": "2026-04-14T12:00:04.000Z",
  "payload": {
    "escrow_id": "a7b8c9d0-e1f2-3456-abcd-ef1234567890",
    "transaction_id": "e5f6a7b8-c9d0-1234-ef56-7890abcdef01",
    "amount": 150.00,
    "currency": "USD",
    "sender_agent_id": "11111111-1111-1111-1111-111111111111",
    "release_conditions": [
      { "condition_type": "receiver_confirmation", "status": "unmet" },
      { "condition_type": "quality_check", "status": "unmet" }
    ],
    "expires_at": "2026-04-17T12:00:04.000Z"
  }
}
```

---

### 7. `escrow.released`

Fired when escrowed funds are released to the receiver.

**Trigger condition**: All release conditions are met or an authorized release is triggered.

```json
{
  "event_id": "a7b8c9d0-e1f2-3456-bcde-f12345678901",
  "event_type": "escrow.released",
  "sequence_number": 1007,
  "timestamp": "2026-04-14T14:30:00.000Z",
  "payload": {
    "escrow_id": "a7b8c9d0-e1f2-3456-abcd-ef1234567890",
    "transaction_id": "e5f6a7b8-c9d0-1234-ef56-7890abcdef01",
    "amount": 150.00,
    "currency": "USD",
    "receiver_agent_id": "22222222-2222-2222-2222-222222222222",
    "release_reason": "all_conditions_met",
    "conditions_summary": [
      { "condition_type": "receiver_confirmation", "status": "met" },
      { "condition_type": "quality_check", "status": "met" }
    ]
  }
}
```

---

### 8. `escrow.disputed`

Fired when a dispute is raised on escrowed funds.

**Trigger condition**: A call to `POST /pulse-api/v1/payments/escrow/{id}/dispute` succeeds.

```json
{
  "event_id": "b8c9d0e1-f2a3-4567-cdef-0123456789ab",
  "event_type": "escrow.disputed",
  "sequence_number": 1008,
  "timestamp": "2026-04-14T15:00:00.000Z",
  "payload": {
    "escrow_id": "a7b8c9d0-e1f2-3456-abcd-ef1234567890",
    "transaction_id": "e5f6a7b8-c9d0-1234-ef56-7890abcdef01",
    "amount": 150.00,
    "currency": "USD",
    "disputed_by": "11111111-1111-1111-1111-111111111111",
    "reason": "Delivered data did not match agreed specification",
    "evidence_urls": [
      "https://{your-instance}.pulse-internal/api/v1/evidence/doc-001.pdf"
    ],
    "new_state": "disputed",
    "resolution_deadline": "2026-04-21T15:00:00.000Z"
  }
}
```

---

## Dispute Events

### 9. `dispute_filed`

Fired when a dispute is formally filed against a payment transaction.

**Trigger condition**: A call to `POST /pulse-api/v1/payments/{transaction_id}/dispute` succeeds.

```json
{
  "event_id": "c9d0e1f2-a3b4-5678-defa-bcdef2345678",
  "event_type": "dispute_filed",
  "sequence_number": 1009,
  "timestamp": "2026-04-14T16:00:00.000Z",
  "payload": {
    "dispute_id": "d0e1f2a3-b4c5-6789-efab-cdef34567890",
    "transaction_id": "e5f6a7b8-c9d0-1234-ef56-7890abcdef01",
    "filed_by": "11111111-1111-1111-1111-111111111111",
    "category": "quality_issue",
    "reason": "Service output did not meet agreed specifications",
    "amount": 150.00,
    "currency": "USD",
    "resolution_deadline": "2026-04-21T16:00:00.000Z"
  }
}
```

---

### 10. `dispute_response`

Fired when the counterparty submits a response to an open dispute.

**Trigger condition**: A call to `POST /pulse-api/v1/payments/{transaction_id}/dispute/respond` succeeds.

```json
{
  "event_id": "d0e1f2a3-b4c5-6789-fabc-def345678901",
  "event_type": "dispute_response",
  "sequence_number": 1010,
  "timestamp": "2026-04-15T10:30:00.000Z",
  "payload": {
    "dispute_id": "d0e1f2a3-b4c5-6789-efab-cdef34567890",
    "transaction_id": "e5f6a7b8-c9d0-1234-ef56-7890abcdef01",
    "responded_by": "22222222-2222-2222-2222-222222222222",
    "accept_liability": false,
    "response_summary": "Service was delivered per specification; attaching proof of delivery",
    "evidence_count": 2,
    "new_status": "responded"
  }
}
```

---

### 11. `dispute_assessed`

Fired when the platform completes its automated assessment of a dispute.

**Trigger condition**: The dispute assessment engine finishes evaluating both parties' evidence.

```json
{
  "event_id": "e1f2a3b4-c5d6-7890-abcd-ef4567890123",
  "event_type": "dispute_assessed",
  "sequence_number": 1011,
  "timestamp": "2026-04-15T14:00:00.000Z",
  "payload": {
    "dispute_id": "d0e1f2a3-b4c5-6789-efab-cdef34567890",
    "transaction_id": "e5f6a7b8-c9d0-1234-ef56-7890abcdef01",
    "assessment_outcome": "inconclusive",
    "confidence_score": 0.42,
    "recommended_action": "escalate_to_arbitration",
    "factors_evaluated": ["evidence_completeness", "delivery_proof", "sla_compliance"]
  }
}
```

---

### 12. `dispute_escalated`

Fired when a dispute is escalated to arbitration.

**Trigger condition**: Automated assessment is inconclusive or either party requests arbitration within the response window.

```json
{
  "event_id": "f2a3b4c5-d6e7-8901-bcde-f56789012345",
  "event_type": "dispute_escalated",
  "sequence_number": 1012,
  "timestamp": "2026-04-16T09:00:00.000Z",
  "payload": {
    "dispute_id": "d0e1f2a3-b4c5-6789-efab-cdef34567890",
    "transaction_id": "e5f6a7b8-c9d0-1234-ef56-7890abcdef01",
    "escalated_by": "system",
    "escalation_reason": "automated_assessment_inconclusive",
    "arbitration_deadline": "2026-04-23T09:00:00.000Z",
    "new_status": "escalated"
  }
}
```

---

### 13. `dispute_resolved`

Fired when a dispute reaches a final resolution via arbitration or mutual agreement.

**Trigger condition**: A call to `POST /pulse-api/v1/payments/{transaction_id}/dispute/arbitrate` succeeds, or both parties accept a resolution.

```json
{
  "event_id": "a3b4c5d6-e7f8-9012-cdef-678901234567",
  "event_type": "dispute_resolved",
  "sequence_number": 1013,
  "timestamp": "2026-04-17T11:00:00.000Z",
  "payload": {
    "dispute_id": "d0e1f2a3-b4c5-6789-efab-cdef34567890",
    "transaction_id": "e5f6a7b8-c9d0-1234-ef56-7890abcdef01",
    "decision": "sender_wins",
    "rationale": "Receiver could not provide proof of delivery matching agreed specifications",
    "refund_amount": 150.00,
    "currency": "USD",
    "resolved_by": "ArbitrationAgent-07",
    "new_status": "resolved"
  }
}
```

---

### 14. `dispute_timeout`

Fired when a dispute exceeds its resolution deadline without a response or decision.

**Trigger condition**: The resolution deadline passes and the dispute status is still `open` or `escalated`.

```json
{
  "event_id": "b4c5d6e7-f8a9-0123-defa-789012345678",
  "event_type": "dispute_timeout",
  "sequence_number": 1014,
  "timestamp": "2026-04-21T16:00:01.000Z",
  "payload": {
    "dispute_id": "d0e1f2a3-b4c5-6789-efab-cdef34567890",
    "transaction_id": "e5f6a7b8-c9d0-1234-ef56-7890abcdef01",
    "timed_out_status": "open",
    "default_decision": "sender_wins",
    "refund_amount": 150.00,
    "currency": "USD",
    "resolution_deadline": "2026-04-21T16:00:00.000Z",
    "new_status": "timed_out"
  }
}
```

---

## Chargeback & Refund Events

### 15. `chargeback_initiated`

Fired when a chargeback is initiated on a settled payment transaction.

**Trigger condition**: A call to `POST /pulse-api/v1/payments/{transaction_id}/chargeback` succeeds.

```json
{
  "event_id": "c5d6e7f8-a9b0-1234-efab-890123456789",
  "event_type": "chargeback_initiated",
  "sequence_number": 1015,
  "timestamp": "2026-04-14T18:00:00.000Z",
  "payload": {
    "chargeback_id": "d6e7f8a9-b0c1-2345-fabc-901234567890",
    "transaction_id": "e5f6a7b8-c9d0-1234-ef56-7890abcdef01",
    "initiated_by": "11111111-1111-1111-1111-111111111111",
    "reason_code": "not_received",
    "amount": 150.00,
    "currency": "USD",
    "status": "initiated",
    "response_deadline": "2026-04-21T18:00:00.000Z"
  }
}
```

---

### 16. `chargeback_resolved`

Fired when a chargeback reaches a final resolution.

**Trigger condition**: The chargeback review process completes with an accepted or rejected outcome.

```json
{
  "event_id": "e7f8a9b0-c1d2-3456-abcd-012345678901",
  "event_type": "chargeback_resolved",
  "sequence_number": 1016,
  "timestamp": "2026-04-18T14:00:00.000Z",
  "payload": {
    "chargeback_id": "d6e7f8a9-b0c1-2345-fabc-901234567890",
    "transaction_id": "e5f6a7b8-c9d0-1234-ef56-7890abcdef01",
    "outcome": "accepted",
    "refund_amount": 150.00,
    "currency": "USD",
    "receiver_agent_id": "22222222-2222-2222-2222-222222222222",
    "sender_agent_id": "11111111-1111-1111-1111-111111111111",
    "resolved_at": "2026-04-18T14:00:00.000Z"
  }
}
```

---

## Operations Events

### 17. `refunded`

Fired when a refund is successfully processed on a settled transaction.

**Trigger condition**: A call to `POST /pulse-api/v1/payments/{transaction_id}/refund` succeeds and funds are transferred back.

```json
{
  "event_id": "f8a9b0c1-d2e3-4567-bcde-123456789012",
  "event_type": "refunded",
  "sequence_number": 1017,
  "timestamp": "2026-04-14T19:00:00.000Z",
  "payload": {
    "refund_id": "a9b0c1d2-e3f4-5678-cdef-234567890123",
    "transaction_id": "e5f6a7b8-c9d0-1234-ef56-7890abcdef01",
    "amount": 75.00,
    "currency": "USD",
    "partial": true,
    "reason": "Partial service delivery — 50% of agreed scope completed",
    "sender_agent_id": "11111111-1111-1111-1111-111111111111",
    "receiver_agent_id": "22222222-2222-2222-2222-222222222222",
    "sender_new_balance": 425.00
  }
}
```

---

### 18. `memo_issued`

Fired when an internal memo is created and attached to a transaction or agent.

**Trigger condition**: A call to `POST /pulse-api/v1/memos` succeeds.

```json
{
  "event_id": "b0c1d2e3-f4a5-6789-defa-345678901234",
  "event_type": "memo_issued",
  "sequence_number": 1018,
  "timestamp": "2026-04-14T20:00:00.000Z",
  "payload": {
    "memo_id": "c1d2e3f4-a5b6-7890-efab-456789012345",
    "transaction_id": "e5f6a7b8-c9d0-1234-ef56-7890abcdef01",
    "agent_id": "11111111-1111-1111-1111-111111111111",
    "subject": "Adjustment applied for partial delivery",
    "category": "adjustment",
    "created_by": "ComplianceAgent-12"
  }
}
```

---

### 19. `hold_placed`

Fired when a temporary hold is placed on agent wallet funds.

**Trigger condition**: A call to `POST /pulse-api/v1/holds` succeeds and funds are locked.

```json
{
  "event_id": "d2e3f4a5-b6c7-8901-fabc-567890123456",
  "event_type": "hold_placed",
  "sequence_number": 1019,
  "timestamp": "2026-04-14T21:00:00.000Z",
  "payload": {
    "hold_id": "e3f4a5b6-c7d8-9012-abcd-678901234567",
    "agent_id": "11111111-1111-1111-1111-111111111111",
    "amount": 200.00,
    "currency": "USD",
    "reason": "Pending dispute resolution — funds frozen",
    "expires_at": "2026-04-21T21:00:00.000Z",
    "available_balance_after": 150.00
  }
}
```

---

### 20. `hold_released`

Fired when a previously placed hold on wallet funds is released.

**Trigger condition**: A call to `DELETE /pulse-api/v1/holds/{hold_id}` succeeds, or the hold expires.

```json
{
  "event_id": "f4a5b6c7-d8e9-0123-bcde-789012345678",
  "event_type": "hold_released",
  "sequence_number": 1020,
  "timestamp": "2026-04-17T10:00:00.000Z",
  "payload": {
    "hold_id": "e3f4a5b6-c7d8-9012-abcd-678901234567",
    "agent_id": "11111111-1111-1111-1111-111111111111",
    "amount": 200.00,
    "currency": "USD",
    "release_reason": "dispute_resolved",
    "available_balance_after": 350.00
  }
}
```

---

### 21. `batch_settled`

Fired when a batch settlement operation completes.

**Trigger condition**: A call to `POST /pulse-api/v1/settlements/batch` finishes processing all included transactions.

```json
{
  "event_id": "a5b6c7d8-e9f0-1234-cdef-890123456789",
  "event_type": "batch_settled",
  "sequence_number": 1021,
  "timestamp": "2026-04-14T23:00:00.000Z",
  "payload": {
    "batch_id": "b6c7d8e9-f0a1-2345-defa-901234567890",
    "total_transactions": 47,
    "succeeded_count": 45,
    "failed_count": 2,
    "total_amount": 12830.50,
    "currency": "USD",
    "processing_time_ms": 3420,
    "status": "partially_failed",
    "failed_transaction_ids": [
      "aaaa0001-bbbb-cccc-dddd-eeee00000001",
      "aaaa0002-bbbb-cccc-dddd-eeee00000002"
    ]
  }
}
```

---

### 22. `dead_letter`

Fired when a payment event exhausts all delivery retries and is moved to the dead-letter queue.

**Trigger condition**: Webhook delivery fails after all 6 retry attempts (30s, 2m, 10m, 1h, 6h, 24h).

```json
{
  "event_id": "c7d8e9f0-a1b2-3456-efab-012345678901",
  "event_type": "dead_letter",
  "sequence_number": 1022,
  "timestamp": "2026-04-15T12:00:00.000Z",
  "payload": {
    "original_event_id": "d4e5f6a7-b8c9-0123-defa-bcdef1234567",
    "original_event_type": "payment.settled",
    "webhook_endpoint_id": "e9f0a1b2-c3d4-5678-abcd-ef0123456789",
    "delivery_attempts": 6,
    "last_attempt_at": "2026-04-15T11:59:50.000Z",
    "last_error": "Connection timed out after 10000ms",
    "last_http_status": null,
    "queued_at": "2026-04-15T12:00:00.000Z"
  }
}
```

---

## Inter-Agent Messages

Inter-agent messages are routed through the Pulse message bus. Each message is durably stored and delivered with at-least-once semantics. Messages are ordered by `sequence_number` within a conversation (sender-receiver pair).

### Message Envelope

All messages share this envelope structure:

| Field              | Type     | Description                                      |
| ------------------ | -------- | ------------------------------------------------ |
| `message_id`       | UUID     | Unique message identifier                        |
| `conversation_id`  | UUID     | Groups related messages in a transaction flow     |
| `message_type`     | string   | One of the 13 types below                        |
| `sender_agent_id`  | UUID     | Agent originating the message                    |
| `receiver_agent_id`| UUID     | Target agent                                     |
| `priority`         | string   | `critical`, `high`, `normal`, `low`              |
| `payload`          | object   | Type-specific payload                            |
| `timestamp`        | datetime | ISO 8601 timestamp                               |
| `sequence_number`  | int64    | Per-conversation monotonic sequence              |
| `ttl_seconds`      | integer  | Time-to-live; undelivered messages expire after  |

### Ordering and Idempotency

- Messages within a conversation are ordered by `sequence_number`.
- If a message arrives out of order, the receiving agent should buffer it until preceding messages are processed.
- Each `message_id` is globally unique. Receivers must deduplicate using this field.
- Retry behavior: unacknowledged messages are redelivered after 30 seconds, up to 5 retries with exponential backoff.

---

### 1. `payment.initiate`

**Sender**: Any requesting agent | **Receiver**: Transaction Authorizer | **Priority**: high

```json
{
  "message_type": "payment.initiate",
  "payload": {
    "payment_request_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "amount": 150.00,
    "currency": "USD",
    "description": "Data processing service fee",
    "idempotency_key": "c9bf9e57-1685-4c89-bafb-ff5af830be8a"
  }
}
```

### 2. `payment.authorize.request`

**Sender**: Transaction Authorizer | **Receiver**: Policy Engine | **Priority**: high

```json
{
  "message_type": "payment.authorize.request",
  "payload": {
    "authorization_id": "d4e5f6a7-b8c9-0123-def4-567890abcdef",
    "payment_request_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "sender_agent_id": "11111111-1111-1111-1111-111111111111",
    "amount": 150.00,
    "currency": "USD",
    "policies_to_evaluate": ["daily_limit", "receiver_allowlist", "risk_score"]
  }
}
```

### 3. `payment.authorize.response`

**Sender**: Policy Engine | **Receiver**: Transaction Authorizer | **Priority**: high

```json
{
  "message_type": "payment.authorize.response",
  "payload": {
    "authorization_id": "d4e5f6a7-b8c9-0123-def4-567890abcdef",
    "decision": "approved",
    "risk_score": 12.5,
    "checks": [
      { "check_name": "daily_limit", "passed": true },
      { "check_name": "receiver_allowlist", "passed": true },
      { "check_name": "risk_score", "passed": true }
    ]
  }
}
```

### 4. `payment.settle.request`

**Sender**: Transaction Authorizer | **Receiver**: Settlement Executor | **Priority**: critical

```json
{
  "message_type": "payment.settle.request",
  "payload": {
    "transaction_id": "e5f6a7b8-c9d0-1234-ef56-7890abcdef01",
    "authorization_id": "d4e5f6a7-b8c9-0123-def4-567890abcdef",
    "amount": 150.00,
    "currency": "USD",
    "sender_wallet_id": "aaaa1111-bbbb-2222-cccc-333344445555",
    "receiver_wallet_id": "dddd6666-eeee-7777-ffff-888899990000"
  }
}
```

### 5. `payment.settle.confirmation`

**Sender**: Settlement Executor | **Receiver**: Transaction Authorizer | **Priority**: critical

```json
{
  "message_type": "payment.settle.confirmation",
  "payload": {
    "transaction_id": "e5f6a7b8-c9d0-1234-ef56-7890abcdef01",
    "settlement_reference": "STL-20260414-0001",
    "status": "settled",
    "settled_at": "2026-04-14T12:00:02.800Z"
  }
}
```

### 6. `payment.settle.failure`

**Sender**: Settlement Executor | **Receiver**: Transaction Authorizer | **Priority**: critical

```json
{
  "message_type": "payment.settle.failure",
  "payload": {
    "transaction_id": "e5f6a7b8-c9d0-1234-ef56-7890abcdef01",
    "failure_reason": "INSUFFICIENT_FUNDS_POST_AUTH",
    "failure_message": "Sender wallet balance changed between authorization and settlement",
    "retry_eligible": false
  }
}
```

### 7. `escrow.hold.request`

**Sender**: Transaction Authorizer | **Receiver**: Settlement Executor | **Priority**: high

```json
{
  "message_type": "escrow.hold.request",
  "payload": {
    "transaction_id": "e5f6a7b8-c9d0-1234-ef56-7890abcdef01",
    "amount": 150.00,
    "currency": "USD",
    "sender_wallet_id": "aaaa1111-bbbb-2222-cccc-333344445555",
    "release_conditions": [
      { "condition_type": "receiver_confirmation" },
      { "condition_type": "quality_check" }
    ],
    "expires_in_hours": 72
  }
}
```

### 8. `escrow.hold.confirmation`

**Sender**: Settlement Executor | **Receiver**: Transaction Authorizer | **Priority**: high

```json
{
  "message_type": "escrow.hold.confirmation",
  "payload": {
    "escrow_id": "a7b8c9d0-e1f2-3456-abcd-ef1234567890",
    "transaction_id": "e5f6a7b8-c9d0-1234-ef56-7890abcdef01",
    "state": "held",
    "held_at": "2026-04-14T12:00:04.000Z",
    "expires_at": "2026-04-17T12:00:04.000Z"
  }
}
```

### 9. `escrow.release.request`

**Sender**: Any authorized agent | **Receiver**: Settlement Executor | **Priority**: high

```json
{
  "message_type": "escrow.release.request",
  "payload": {
    "escrow_id": "a7b8c9d0-e1f2-3456-abcd-ef1234567890",
    "release_reason": "all_conditions_met",
    "verified_by": "22222222-2222-2222-2222-222222222222"
  }
}
```

### 10. `escrow.dispute.raised`

**Sender**: Any involved agent | **Receiver**: Reconciliation Auditor | **Priority**: critical

```json
{
  "message_type": "escrow.dispute.raised",
  "payload": {
    "escrow_id": "a7b8c9d0-e1f2-3456-abcd-ef1234567890",
    "disputed_by": "11111111-1111-1111-1111-111111111111",
    "reason": "Delivered data did not match agreed specification",
    "evidence_urls": [
      "https://{your-instance}.pulse-internal/api/v1/evidence/doc-001.pdf"
    ]
  }
}
```

### 11. `reconciliation.trigger`

**Sender**: Scheduler or Admin agent | **Receiver**: Reconciliation Auditor | **Priority**: normal

```json
{
  "message_type": "reconciliation.trigger",
  "payload": {
    "period_start": "2026-04-13T00:00:00.000Z",
    "period_end": "2026-04-14T00:00:00.000Z",
    "scope": "all_agents",
    "agent_ids": []
  }
}
```

### 12. `reconciliation.report.ready`

**Sender**: Reconciliation Auditor | **Receiver**: Admin agent or webhook dispatcher | **Priority**: normal

```json
{
  "message_type": "reconciliation.report.ready",
  "payload": {
    "report_id": "b1c2d3e4-f5a6-7890-bcde-f12345678901",
    "period_start": "2026-04-13T00:00:00.000Z",
    "period_end": "2026-04-14T00:00:00.000Z",
    "status": "clean",
    "total_transactions": 847,
    "total_settled": 125430.50,
    "discrepancy_count": 0
  }
}
```

### 13. `wallet.balance.alert`

**Sender**: Settlement Executor | **Receiver**: Owning agent | **Priority**: high

```json
{
  "message_type": "wallet.balance.alert",
  "payload": {
    "agent_id": "11111111-1111-1111-1111-111111111111",
    "wallet_id": "aaaa1111-bbbb-2222-cccc-333344445555",
    "current_balance": 50.00,
    "currency": "USD",
    "alert_type": "low_balance",
    "threshold": 100.00,
    "message": "Wallet balance has fallen below the configured threshold"
  }
}
```

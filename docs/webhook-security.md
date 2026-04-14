# Webhook Security

Version: 4.17.0 | Protocol: A2A Payment Protocol | Engine: Pulse Engines

---

## Overview

The Pulse Engines webhook system delivers real-time event notifications for payment
lifecycle transitions. Every webhook delivery is cryptographically signed, retry-safe,
and idempotent. This document covers the eight payment events, payload structure,
signature verification, retry policy, endpoint management, and operational security
controls.

---

## Supported Payment Events

The platform emits eight distinct payment events across the transaction lifecycle:

| Event Type                  | Trigger                                                       |
| --------------------------- | ------------------------------------------------------------- |
| `payment.authorized`        | Transaction passes all policy checks and compliance precheck  |
| `payment.denied`            | Transaction rejected by policy engine or compliance engine     |
| `payment.settled`           | Funds successfully transferred between agent wallets           |
| `payment.failed`            | Settlement execution failed after authorization                |
| `payment.escrow_held`       | Funds locked into escrow pending release conditions            |
| `payment.escrow_released`   | Escrow conditions met and funds released to counterparty       |
| `payment.escrow_expired`    | Escrow time window elapsed without conditions being met        |
| `payment.disputed`          | Escrow dispute raised by requesting or counterparty agent      |

### Event Lifecycle Flow

```
payment.authorized ──> payment.settled          (direct settlement)
payment.authorized ──> payment.failed           (settlement failure)
payment.authorized ──> payment.escrow_held      (escrow path)
payment.escrow_held ──> payment.escrow_released (conditions met)
payment.escrow_held ──> payment.escrow_expired  (timeout)
payment.escrow_held ──> payment.disputed        (dispute raised)
payment.denied                                  (rejected at auth)
```

---

## Payload Structure

Every webhook delivery uses a consistent envelope format:

```json
{
  "event": "payment.authorized",
  "event_id": "evt_a1b2c3d4e5f6",
  "timestamp": "2026-04-14T12:34:56.789Z",
  "version": "2026-04-01",
  "data": {
    "transaction_id": "txn_9f8e7d6c5b4a",
    "requesting_agent_id": "agent-treasury-ops",
    "requesting_org_id": "org_abc123",
    "counterparty_agent_id": "agent-vendor-pay",
    "counterparty_org_id": "org_def456",
    "amount": 2500.00,
    "currency": "USD",
    "tx_type": "vendor_payment",
    "category": "operations",
    "status": "authorized",
    "authorization": {
      "decision": "approved",
      "reason_code": "policy_pass",
      "compliance_status": "clear",
      "processing_time_ms": 142
    },
    "metadata": {
      "invoice_id": "INV-2026-0412",
      "po_number": "PO-8834"
    }
  }
}
```

### Field Definitions

| Field       | Type   | Description                                                      |
| ----------- | ------ | ---------------------------------------------------------------- |
| `event`     | string | One of the eight event types listed above                        |
| `event_id`  | string | Globally unique identifier for this event, prefixed with `evt_`  |
| `timestamp` | string | ISO 8601 timestamp in UTC when the event was generated           |
| `version`   | string | API version date for the payload schema                          |
| `data`      | object | Event-specific payload containing transaction details            |

### Event-Specific Data Fields

**payment.authorized / payment.denied:**
- `authorization.decision` - "approved" or "denied"
- `authorization.reason_code` - Machine-readable reason
- `authorization.reason_detail` - Human-readable explanation
- `authorization.compliance_status` - "clear", "flagged", or "blocked"
- `authorization.processing_time_ms` - End-to-end authorization time

**payment.settled:**
- `settlement.settled_at` - ISO 8601 settlement timestamp
- `settlement.sender_balance_after` - Sender wallet balance post-settlement
- `settlement.receiver_balance_after` - Receiver wallet balance post-settlement

**payment.failed:**
- `failure.reason` - Machine-readable failure reason
- `failure.detail` - Human-readable failure description
- `failure.retriable` - Boolean indicating if the transaction can be retried

**payment.escrow_held:**
- `escrow.escrow_id` - Unique identifier for the escrow hold
- `escrow.amount` - Amount held in escrow
- `escrow.release_conditions` - Conditions required for release
- `escrow.expires_at` - Escrow expiration timestamp

**payment.escrow_released:**
- `escrow.escrow_id` - Escrow identifier
- `escrow.released_at` - Release timestamp
- `escrow.released_to` - Agent ID that received the funds

**payment.escrow_expired:**
- `escrow.escrow_id` - Escrow identifier
- `escrow.expired_at` - Expiration timestamp
- `escrow.refunded_to` - Agent ID receiving the refund

**payment.disputed:**
- `escrow.escrow_id` - Escrow identifier
- `dispute.raised_by` - Agent ID that raised the dispute
- `dispute.reason` - Dispute reason text
- `dispute.disputed_at` - Dispute timestamp

---

## HMAC-SHA256 Signing Process

Every webhook delivery includes a cryptographic signature in the `X-Pulse-Signature`
header. The signature is computed using HMAC-SHA256 with the endpoint-specific signing
secret.

### Signature Computation

1. The raw JSON payload body is serialized (no whitespace normalization).
2. The `X-Pulse-Timestamp` header value is prepended with a period separator.
3. HMAC-SHA256 is computed over the combined string using the endpoint signing secret.
4. The hex-encoded digest is placed in the `X-Pulse-Signature` header.

**Signature input format:**

```
{timestamp}.{raw_json_body}
```

**Delivered headers:**

```
X-Pulse-Signature: sha256=a3f1b8c9d2e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0
X-Pulse-Timestamp: 1713096896
X-Pulse-Event: payment.authorized
X-Pulse-Delivery-Id: dlv_x1y2z3w4
```

### Timestamp Validation

Recipients should reject deliveries where the timestamp is more than 5 minutes old
to prevent replay attacks. Compare `X-Pulse-Timestamp` against the current server time.

---

## Verification Code

### Node.js Verification

```javascript
const crypto = require('crypto');

function verifyWebhookSignature(req, secret) {
  const signature = req.headers['x-pulse-signature'];
  const timestamp = req.headers['x-pulse-timestamp'];

  if (!signature || !timestamp) {
    return { valid: false, error: 'Missing signature headers' };
  }

  // Reject stale timestamps (5 minute window)
  const currentTime = Math.floor(Date.now() / 1000);
  const deliveryTime = parseInt(timestamp, 10);
  if (Math.abs(currentTime - deliveryTime) > 300) {
    return { valid: false, error: 'Timestamp outside acceptable window' };
  }

  // Compute expected signature
  const payload = `${timestamp}.${req.rawBody}`;
  const expectedSignature = 'sha256=' + crypto
    .createHmac('sha256', secret)
    .update(payload, 'utf8')
    .digest('hex');

  // Timing-safe comparison to prevent timing attacks
  const expected = Buffer.from(expectedSignature, 'utf8');
  const received = Buffer.from(signature, 'utf8');

  if (expected.length !== received.length) {
    return { valid: false, error: 'Signature length mismatch' };
  }

  const isValid = crypto.timingSafeEqual(expected, received);
  return { valid: isValid, error: isValid ? null : 'Signature mismatch' };
}

// Express.js middleware example
app.post('/pulse-api/webhooks/receive', express.raw({ type: 'application/json' }), (req, res) => {
  req.rawBody = req.body.toString('utf8');
  const result = verifyWebhookSignature(req, process.env.WEBHOOK_SECRET);

  if (!result.valid) {
    console.error('Webhook verification failed:', result.error);
    return res.status(401).json({ error: result.error });
  }

  const event = JSON.parse(req.rawBody);
  console.log('Verified webhook event:', event.event, event.event_id);

  // Process event (idempotently using event_id)
  processEvent(event);

  // Return 200 quickly to prevent retries
  res.status(200).json({ received: true });
});
```

### Python Verification

```python
import hmac
import hashlib
import time
import json

def verify_webhook_signature(headers, raw_body, secret):
    """
    Verify Pulse Engines webhook HMAC-SHA256 signature.
    Uses hmac.compare_digest for timing-safe comparison.
    """
    signature = headers.get('X-Pulse-Signature', '')
    timestamp = headers.get('X-Pulse-Timestamp', '')

    if not signature or not timestamp:
        return False, 'Missing signature headers'

    # Reject stale timestamps (5 minute window)
    current_time = int(time.time())
    delivery_time = int(timestamp)
    if abs(current_time - delivery_time) > 300:
        return False, 'Timestamp outside acceptable window'

    # Compute expected signature
    payload = f'{timestamp}.{raw_body}'.encode('utf-8')
    expected_sig = 'sha256=' + hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()

    # Timing-safe comparison to prevent timing attacks
    is_valid = hmac.compare_digest(expected_sig, signature)
    return is_valid, None if is_valid else 'Signature mismatch'


# Flask example
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/pulse-api/webhooks/receive', methods=['POST'])
def handle_webhook():
    raw_body = request.get_data(as_text=True)
    is_valid, error = verify_webhook_signature(
        request.headers,
        raw_body,
        WEBHOOK_SECRET
    )

    if not is_valid:
        return jsonify({'error': error}), 401

    event = json.loads(raw_body)
    print(f'Verified: {event["event"]} / {event["event_id"]}')

    # Process idempotently
    process_event(event)

    return jsonify({'received': True}), 200
```

---

## Retry Schedule

Failed deliveries (non-2xx response or network timeout) are retried up to 10 times
over a 72-hour window. Each attempt uses exponential backoff:

| Attempt | Delay After Previous | Cumulative Time  |
| ------- | -------------------- | ---------------- |
| 1       | Immediate            | 0s               |
| 2       | +30 seconds          | 30s              |
| 3       | +2 minutes           | 2m 30s           |
| 4       | +10 minutes          | 12m 30s          |
| 5       | +1 hour              | 1h 12m 30s       |
| 6       | +4 hours             | 5h 12m 30s       |
| 7       | +12 hours            | 17h 12m 30s      |
| 8       | +24 hours            | 41h 12m 30s      |
| 9       | +48 hours            | 89h 12m 30s      |
| 10      | +72 hours            | 161h 12m 30s     |

### Retry Behavior

- Each retry uses the same `event_id` and `X-Pulse-Delivery-Id` header.
- The `X-Pulse-Retry-Count` header indicates the attempt number (0-indexed).
- A delivery is considered successful on any HTTP 2xx response.
- HTTP 410 (Gone) responses immediately cancel all future retries for that delivery.
- Timeouts occur after 30 seconds of no response.

---

## Auto-Disable After 10 Consecutive Failures

When an endpoint accumulates 10 consecutive delivery failures (across any events,
not just a single event), the platform automatically disables the endpoint.

### Disabled State Behavior

- The endpoint `status` field changes from `"active"` to `"disabled"`.
- No further deliveries are attempted to the endpoint.
- Events that would have been sent are still recorded internally.
- The `last_error` field contains the most recent failure reason.
- The `failure_count` field shows the cumulative failure count.

### Re-Enabling a Disabled Endpoint

Use the PATCH endpoint to re-enable:

```bash
curl -X PATCH https://your-instance.pulse.app/pulse-api/webhooks/{webhook_id} \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"status": "active"}'
```

Re-enabling resets the consecutive failure counter to zero. The endpoint will resume
receiving events from the point of re-enablement (missed events during the disabled
period are not retroactively delivered).

---

## Endpoint Registration

### Creating a Webhook Endpoint

```bash
curl -X POST https://your-instance.pulse.app/pulse-api/webhooks \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-app.com/pulse-api/webhooks/receive",
    "description": "Payment event handler for treasury operations",
    "events": [
      "payment.authorized",
      "payment.settled",
      "payment.failed",
      "payment.escrow_held",
      "payment.escrow_released"
    ],
    "agent_filter": ["agent-treasury-ops", "agent-vendor-pay"]
  }'
```

**Response (201):**

```json
{
  "id": "whk_a1b2c3d4",
  "url": "https://your-app.com/pulse-api/webhooks/receive",
  "description": "Payment event handler for treasury operations",
  "events": ["payment.authorized", "payment.settled", "payment.failed",
             "payment.escrow_held", "payment.escrow_released"],
  "status": "active",
  "secret": "your_webhook_signing_secret_here",
  "created_at": "2026-04-14T12:00:00.000Z"
}
```

The `secret` value is returned only once at creation time. Store it securely. If lost,
delete the endpoint and create a new one.

### Event Filtering

Each endpoint can subscribe to specific events. Only matching events are delivered.
The `agent_filter` array optionally restricts deliveries to transactions involving
specific agent IDs (empty array means all agents).

---

## Per-Endpoint Secrets

Every webhook endpoint receives its own unique signing secret at creation time. This
ensures that compromising one endpoint secret does not affect deliveries to other
endpoints within the same organization.

### Secret Properties

- 256-bit (32-byte) cryptographically random value.
- Hex-encoded string. Treat as a secret — store securely, never commit to source control.
- Generated server-side using `crypto.getRandomValues()`.
- Stored encrypted at rest in the database.
- Never transmitted after the initial creation response.

### Secret Rotation

To rotate a secret, delete the endpoint and recreate it with the same URL and event
subscriptions. The new endpoint receives a fresh secret.

---

## IP Whitelisting

Webhook deliveries originate from a fixed set of IP addresses. Configure your firewall
or reverse proxy to accept connections only from these addresses:

### Production IP Ranges

```
52.14.88.0/24
52.14.89.0/24
18.220.44.0/24
```

### Verification Header

Every delivery includes the `X-Pulse-Source-IP` header containing the originating
server IP, which can be validated against the whitelist as an additional check.

### Updating IP Ranges

IP range changes are communicated 30 days in advance via the platform status page
and through a dedicated `system.ip_range_update` event (subscribe via the webhooks
endpoint).

---

## Idempotency

Every webhook event carries a globally unique `event_id`. Recipients must use this
identifier to ensure idempotent processing.

### Idempotency Requirements

1. Before processing an event, check if `event_id` has already been processed.
2. If already processed, return HTTP 200 and skip processing.
3. If not processed, execute business logic, then record the `event_id`.
4. Use a database unique constraint or distributed lock on `event_id`.

### Implementation Example

```javascript
async function processEvent(event) {
  // Check for duplicate delivery
  const existing = await db.webhookEvents.findOne({
    event_id: event.event_id
  });

  if (existing) {
    console.log('Duplicate event, skipping:', event.event_id);
    return;
  }

  // Process the event
  await handlePaymentEvent(event);

  // Record as processed
  await db.webhookEvents.insertOne({
    event_id: event.event_id,
    event_type: event.event,
    processed_at: new Date(),
  });
}
```

### Delivery Deduplication Window

The platform guarantees that a given `event_id` will not be reused for at least
90 days. Recipients should retain processed event IDs for at least this duration.

---

## Ordering Guarantees

### Within a Single Transaction

Events for a single transaction are delivered in causal order:

1. `payment.authorized` always precedes `payment.settled` or `payment.failed`.
2. `payment.escrow_held` always precedes `payment.escrow_released`, `payment.escrow_expired`, or `payment.disputed`.

The platform enforces this by sequencing deliveries per transaction ID.

### Across Transactions

Events from different transactions have no ordering guarantees. Two concurrent
transactions may have their events delivered in any interleaved order. Do not assume
that `payment.authorized` for Transaction A arrives before `payment.authorized`
for Transaction B, even if Transaction A was created first.

### Handling Out-of-Order Delivery

Use the `timestamp` field within the event payload to determine the true chronological
order. If your system receives `payment.settled` before `payment.authorized` (due to
retry delays), use the timestamp to reconcile state.

---

## Delivery Inspection

### Viewing Recent Deliveries

```bash
curl https://your-instance.pulse.app/pulse-api/webhooks/{webhook_id}/deliveries?limit=50 \
  -H "Authorization: Bearer YOUR_API_KEY"
```

**Response:**

```json
{
  "deliveries": [
    {
      "id": "dlv_x1y2z3w4",
      "event_type": "payment.settled",
      "status": "delivered",
      "attempts": 1,
      "response_status": 200,
      "duration_ms": 142,
      "delivered_at": "2026-04-14T12:35:00.000Z",
      "created_at": "2026-04-14T12:34:57.000Z"
    }
  ]
}
```

### Testing an Endpoint

Send a test delivery to verify connectivity:

```bash
curl -X POST https://your-instance.pulse.app/pulse-api/webhooks/{webhook_id}/test \
  -H "Authorization: Bearer YOUR_API_KEY"
```

This sends a `test` event with a sample payload. Test deliveries follow the same
signing process as production deliveries.

---

## Security Best Practices

1. **Always verify signatures** - Never process unsigned or improperly signed payloads.
2. **Validate timestamps** - Reject deliveries older than 5 minutes.
3. **Use HTTPS endpoints** - The platform rejects HTTP (non-TLS) webhook URLs.
4. **Restrict by IP** - Whitelist the Pulse Engines delivery IP ranges.
5. **Process idempotently** - Use `event_id` to prevent duplicate processing.
6. **Respond quickly** - Return HTTP 200 within 5 seconds; defer heavy processing.
7. **Store secrets securely** - Use environment variables or a secrets manager.
8. **Monitor failure counts** - Alert on rising `failure_count` before auto-disable.
9. **Rotate secrets periodically** - Delete and recreate endpoints quarterly.
10. **Log all deliveries** - Retain delivery metadata for audit and troubleshooting.

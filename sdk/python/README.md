> **Internal SDK** — This SDK interfaces with the Pulse internal API. It is not distributed via npm/PyPI. Provided here as architectural reference. For access, contact [support@tfsfventures.com](mailto:support@tfsfventures.com).

# a2a-payments

Python SDK for the A2A Pulse Payments API -- agent-to-agent payments with escrow, spending policies, and reconciliation.

## Installation

```bash
pip install a2a-payments
```

Requires Python 3.9+.

## Quick Start

```python
from a2a_payments import PulsePayments

client = PulsePayments(api_key="YOUR_API_KEY)

# Send a payment between agents
payment = client.request_payment(
    from_agent_id="agent_billing",
    to_agent_id="agent_fulfillment",
    amount=49.99,
    currency="USD",
    memo="Order #1042 fulfillment fee",
)

print(payment.payment_id, payment.status)
```

## API Reference

### Initializing the Client

```python
from a2a_payments import PulsePayments

# Default endpoint
client = PulsePayments(api_key="YOUR_API_KEY)

# Custom base URL and timeout
client = PulsePayments(
    api_key="YOUR_API_KEY,
    base_url="https://{your-instance}.pulse-internal/api",
    timeout=60.0,
)

# Use as a context manager for automatic cleanup
with PulsePayments(api_key="YOUR_API_KEY) as client:
    wallet = client.get_wallet("wal_abc123")
```

### Payments

```python
# Create a payment
payment = client.request_payment(
    from_agent_id="agent_sender",
    to_agent_id="agent_receiver",
    amount=25.00,
    currency="USD",
    idempotency_key="order-1042",
    memo="Monthly subscription",
    metadata={"order_id": "1042"},
)

# Get a payment by ID
payment = client.get_payment("pay_abc123")

# List payments with filters
from a2a_payments import TransactionStatus

page = client.list_payments(
    agent_id="agent_sender",
    status=TransactionStatus.COMPLETED,
    page=1,
    per_page=50,
)
for p in page.data:
    print(p.payment_id, p.amount)

# Get audit-log events for a payment
events = client.get_payment_events("pay_abc123")
for event in events:
    print(event.event_type, event.occurred_at)

# Dispute a payment
disputed = client.dispute_payment(
    "pay_abc123",
    reason="Service not delivered",
    reason_code="agent_timeout",
)
```

### Wallets

```python
# Get wallet details
wallet = client.get_wallet("wal_abc123")
print(wallet.balance, wallet.available_balance)

# List wallets for an agent
wallets = client.list_wallets(agent_id="agent_billing")

# Fund a wallet
wallet = client.fund_wallet("wal_abc123", amount=500.00)

# Withdraw from a wallet
wallet = client.withdraw_wallet(
    "wal_abc123",
    amount=100.00,
    idempotency_key="withdraw-20260414",
)
```

### Spending Policies

```python
# Create a policy
policy = client.create_policy(
    name="Standard Agent Limits",
    agent_id="agent_billing",
    max_transaction_amount=1000.00,
    daily_limit=5000.00,
    monthly_limit=50000.00,
    allowed_currencies=["USD", "EUR"],
    require_escrow=True,
)

# List policies
policies = client.list_policies(agent_id="agent_billing")

# Update a policy
updated = client.update_policy(
    "pol_abc123",
    daily_limit=10000.00,
    require_escrow=False,
)

# Delete a policy
client.delete_policy("pol_abc123")
```

### Reconciliation

```python
# List reconciliation reports
reports = client.list_reports(page=1, per_page=10)
for r in reports.data:
    print(r.report_id, r.matched, r.unmatched)

# Trigger a new reconciliation run
report = client.trigger_reconciliation()
print(report.report_id, report.status)
```

## Webhook Verification

Verify incoming webhook signatures using HMAC-SHA256:

```python
from a2a_payments import verify_webhook

# In your webhook handler (e.g., Flask / FastAPI)
is_valid = verify_webhook(
    payload=request.body,
    signature=request.headers["X-Pulse-Signature"],
    secret="your_webhook_secret",
)

if not is_valid:
    return {"error": "Invalid signature"}, 401
```

## Error Handling

All API errors raise typed exceptions:

```python
from a2a_payments import (
    PulsePayments,
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    ConflictError,
    PulseApiError,
)

client = PulsePayments(api_key="YOUR_API_KEY)

try:
    payment = client.get_payment("pay_nonexistent")
except AuthenticationError:
    print("Check your API key")
except NotFoundError:
    print("Payment does not exist")
except RateLimitError as e:
    print(f"Throttled -- retry after {e.retry_after}s")
except ConflictError:
    print("Duplicate or state conflict")
except PulseApiError as e:
    print(f"API error {e.status}: {e.code} - {e.message}")
```

## Async Support

The SDK uses `httpx` under the hood. For async usage, you can instantiate
`httpx.AsyncClient` directly with the same base URL and headers:

```python
import httpx

async_client = httpx.AsyncClient(
    base_url="https://{your-instance}.pulse-internal/api",
    headers={
        "Authorization": "Bearer YOUR_API_KEY,
        "Content-Type": "application/json",
    },
)

resp = await async_client.post("/payments", json={
    "from_agent_id": "agent_a",
    "to_agent_id": "agent_b",
    "amount": 10.00,
    "currency": "USD",
})
```

A fully typed async client is planned for a future release.

## Types

All response objects are Python dataclasses. Enums use `str` bases for easy serialization:

| Type | Description |
|------|-------------|
| `PaymentRequest` | Input payload for creating a payment |
| `PaymentResponse` | Full payment record with transactions |
| `Transaction` | Single ledger entry |
| `PaymentEvent` | Audit-log event |
| `Wallet` | Agent wallet with balances |
| `SpendingPolicy` | Transaction governance rules |
| `ReconciliationReport` | Reconciliation run summary |
| `PaginatedResponse[T]` | Generic paginated wrapper |
| `WebhookPayload` | Parsed webhook delivery |
| `TransactionStatus` | `pending`, `processing`, `completed`, `failed`, `cancelled`, `refunded` |
| `EscrowStatus` | `held`, `released`, `disputed`, `refunded`, `expired` |
| `ReasonCode` | Machine-readable dispute/failure codes |
| `EventType` | Webhook and audit event types |

## License

Apache-2.0

> **Internal SDK** — This SDK interfaces with the Pulse internal API. It is not distributed via npm/PyPI. Provided here as architectural reference.

# @tfsfventures/a2a-payments

TypeScript SDK for the **Pulse Payments** A2A (Agent-to-Agent) payment network.
Provides a fully typed client for creating payments, managing wallets, enforcing
spending policies, running reconciliation reports, and verifying webhook
signatures.

---

## Installation

```bash
npm install @tfsfventures/a2a-payments
```

> Requires Node.js 18+ (uses the built-in `fetch` API).

---

## 5-Minute Integration

```ts
import { PulsePayments } from "@tfsfventures/a2a-payments";

const pulse = new PulsePayments({
  apiKey: process.env.PULSE_API_KEY!,
  baseUrl: "https://your-domain.com/pulse-api/",
});

// Send a payment between two agent wallets
const payment = await pulse.requestPayment({
  amount: 5000,          // $50.00 (cents)
  currency: "USD",
  from_wallet_id: "wal_sender_001",
  to_wallet_id: "wal_receiver_002",
  memo: "Invoice #1042",
});

console.log(payment.id, payment.status);
```

---

## API Reference

### Initializing the Client

```ts
import { PulsePayments } from "@tfsfventures/a2a-payments";

const pulse = new PulsePayments({
  apiKey: "YOUR_API_KEY,       // Required
  baseUrl: "/pulse-api/",     // Optional, defaults to "/pulse-api/"
});
```

---

### Payments

#### Create a Payment

```ts
const payment = await pulse.requestPayment({
  amount: 10000,
  currency: "USD",
  from_wallet_id: "wal_abc",
  to_wallet_id: "wal_xyz",
  idempotency_key: "order-7891",
  memo: "Monthly subscription",
  metadata: { orderId: "7891" },
});
```

#### Retrieve a Payment

```ts
const payment = await pulse.getPayment("pay_123");
```

#### List Payments

```ts
const { data, total, total_pages } = await pulse.listPayments({
  page: 1,
  per_page: 25,
  status: "settled",
  wallet_id: "wal_abc",
  sort_by: "created_at",
  sort_order: "desc",
});
```

#### Get Payment Events

```ts
const events = await pulse.getPaymentEvents("pay_123");
events.forEach((e) => console.log(e.type, e.created_at));
```

#### Dispute a Payment

```ts
const disputed = await pulse.disputePayment("pay_123", {
  reason_code: "amount_mismatch",
  description: "Charged $100 instead of $50",
});
```

---

### Wallets

#### Get a Wallet

```ts
const wallet = await pulse.getWallet("wal_abc");
console.log(wallet.balance, wallet.available_balance);
```

#### List Wallets

```ts
const { data: wallets } = await pulse.listWallets({
  agent_id: "agent_001",
  page: 1,
  per_page: 50,
});
```

#### Fund a Wallet

```ts
const updated = await pulse.fundWallet("wal_abc", {
  amount: 100000,    // $1,000.00
  currency: "USD",
  memo: "Initial funding",
});
```

#### Withdraw from a Wallet

```ts
const updated = await pulse.withdrawWallet("wal_abc", {
  amount: 25000,
  currency: "USD",
  memo: "Payout to treasury",
});
```

---

### Spending Policies

#### Create a Policy

```ts
const policy = await pulse.createPolicy({
  name: "Daily cap - Agent 12",
  wallet_id: "wal_abc",
  max_amount: 50000,
  daily_limit: 200000,
  monthly_limit: 5000000,
  allowed_currencies: ["USD"],
  enabled: true,
});
```

#### Get a Policy

```ts
const policy = await pulse.getPolicy("pol_456");
```

#### List Policies

```ts
const { data: policies } = await pulse.listPolicies({
  wallet_id: "wal_abc",
});
```

#### Update a Policy

```ts
const updated = await pulse.updatePolicy("pol_456", {
  daily_limit: 300000,
  enabled: false,
});
```

#### Delete a Policy

```ts
await pulse.deletePolicy("pol_456");
```

---

### Reports and Reconciliation

#### List Reports

```ts
const { data: reports } = await pulse.listReports({
  page: 1,
  per_page: 10,
  sort_order: "desc",
});
```

#### Trigger a Reconciliation

```ts
const report = await pulse.triggerReconciliation({
  from: "2025-01-01T00:00:00Z",
  to: "2025-01-31T23:59:59Z",
});

console.log(report.id, report.status); // "pending"
```

---

### Webhook Verification

All webhook requests from Pulse include an HMAC-SHA256 signature in the
`X-Pulse-Signature` header and a unix timestamp in `X-Pulse-Timestamp`.

```ts
import { verifyWebhookSignature } from "@tfsfventures/a2a-payments";

// In your webhook handler (e.g. Express)
app.post("/webhooks/pulse", (req, res) => {
  try {
    verifyWebhookSignature(
      req.body,                                  // raw body (string | Buffer)
      req.headers["x-pulse-signature"] as string,
      process.env.PULSE_WEBHOOK_SECRET!,
      {
        timestamp: req.headers["x-pulse-timestamp"] as string,
        tolerance: 300, // seconds (default)
      },
    );
  } catch (err) {
    return res.status(403).json({ error: "Invalid signature" });
  }

  const event = JSON.parse(req.body);
  console.log("Received event:", event.type);

  res.status(200).json({ received: true });
});
```

---

### Error Handling

The SDK throws typed errors that can be caught and handled individually.

```ts
import {
  PulseApiError,
  AuthenticationError,
  RateLimitError,
  NotFoundError,
  ConflictError,
} from "@tfsfventures/a2a-payments";

try {
  await pulse.getPayment("pay_nonexistent");
} catch (err) {
  if (err instanceof NotFoundError) {
    console.error("Payment not found");
  } else if (err instanceof AuthenticationError) {
    console.error("Bad API key");
  } else if (err instanceof RateLimitError) {
    console.error(`Rate limited. Retry after ${err.retryAfter}s`);
  } else if (err instanceof ConflictError) {
    console.error("Conflict - duplicate idempotency key?");
  } else if (err instanceof PulseApiError) {
    console.error(`API error ${err.status}: ${err.message}`);
  } else {
    throw err;
  }
}
```

Every `PulseApiError` exposes:

| Property  | Type                 | Description                              |
| --------- | -------------------- | ---------------------------------------- |
| `status`  | `number`             | HTTP status code                         |
| `code`    | `string \| undefined`| Machine-readable error code from the API |
| `message` | `string`             | Human-readable description               |

---

### TypeScript Types

All request and response shapes are exported for use in your own code.

```ts
import type {
  PaymentRequest,
  PaymentResponse,
  Transaction,
  PaymentEvent,
  Wallet,
  PolicyCreate,
  SpendingPolicy,
  ReconciliationReport,
  ListParams,
  PaginatedResponse,
  WebhookPayload,
} from "@tfsfventures/a2a-payments";

import {
  TransactionStatus,
  EventType,
  ReasonCode,
  EscrowStatus,
  Severity,
} from "@tfsfventures/a2a-payments";
```

#### Enums

| Enum                | Values                                                                                  |
| ------------------- | --------------------------------------------------------------------------------------- |
| `TransactionStatus` | `Pending`, `Authorized`, `Captured`, `Settled`, `Disputed`, `Refunded`, `Cancelled`, `Failed` |
| `EventType`         | `Created`, `Authorized`, `Captured`, `Settled`, `Disputed`, `DisputeResolved`, `Refunded`, `Cancelled`, `Failed`, `WalletFunded`, `WalletWithdrawn`, `PolicyViolation` |
| `ReasonCode`        | `Unauthorized`, `DuplicateCharge`, `ServiceNotRendered`, `AmountMismatch`, `FraudSuspected`, `Other` |
| `EscrowStatus`      | `Held`, `Released`, `Reversed`                                                          |
| `Severity`          | `Info`, `Warning`, `Error`, `Critical`                                                  |

---

## License

Apache-2.0

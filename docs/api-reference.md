# API Reference

Version: 4.17.0 | Protocol: A2A Payment Protocol | Engine: Pulse Engines

---

## Base URL

```
https://your-instance.pulse.app/pulse-api/
```

All endpoints are prefixed with `/pulse-api/`. Requests must use HTTPS.

---

## Authentication

Every request (except `/pulse-api/health`) requires a SHA-256 API key in the
`Authorization` header.

```
Authorization: Bearer YOUR_API_KEY
```

### API Key Properties

| Property          | Description                                                |
| ----------------- | ---------------------------------------------------------- |
| Format            | `YOUR_API_KEY` prefix followed by 40 hex characters            |
| Hashing           | Keys are stored as SHA-256 hashes; raw key shown only once |
| IP Whitelist      | Optional list of allowed source IPs per key                |
| Permissions       | Scoped permission array per key                            |
| Agent Restrictions| Optional allowed_agents array to limit agent access        |

### IP Whitelist Enforcement

When an API key has an IP whitelist configured, requests from non-whitelisted IPs
receive a `403 Forbidden` response. The `x-forwarded-for` header is used for IP
resolution behind load balancers.

---

## Rate Limiting

| Limit Type | Value       | Window   | Scope     |
| ---------- | ----------- | -------- | --------- |
| Per-minute | 120 RPM     | Sliding  | Per key   |
| Daily      | 10,000      | Calendar | Per key   |

Rate limit headers are included in every response:

```
X-RateLimit-Limit: 120
X-RateLimit-Remaining: 117
X-RateLimit-Reset: 1713096960
X-RateLimit-Daily-Remaining: 9842
```

Exceeding the rate limit returns `429 Too Many Requests` with a `Retry-After` header.

---

## Common Error Responses

| Status | Code                    | Description                              |
| ------ | ----------------------- | ---------------------------------------- |
| 400    | `bad_request`           | Missing or invalid request parameters    |
| 401    | `unauthorized`          | Missing or invalid API key               |
| 403    | `forbidden`             | Valid key but insufficient permissions    |
| 404    | `not_found`             | Resource does not exist                  |
| 409    | `conflict`              | Resource already exists (duplicate)      |
| 429    | `rate_limited`          | Rate limit exceeded                      |
| 500    | `internal_error`        | Server-side error                        |

Error response body:

```json
{
  "error": "Human-readable error message",
  "code": "machine_readable_code",
  "detail": "Additional context when available"
}
```

---

## Payment Routes (15 Endpoints)

### 1. POST /pulse-api/payments/request

Create a new payment transaction request. Triggers the full authorization pipeline.

**Permission:** `payments:request`

**Request Headers:**
```
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json
```

**Request Body:**

| Field                   | Type   | Required | Description                              |
| ----------------------- | ------ | -------- | ---------------------------------------- |
| `requesting_agent_id`   | string | Yes      | Agent initiating the payment             |
| `counterparty_agent_id` | string | No       | Receiving agent ID                       |
| `counterparty_org_id`   | string | No       | Receiving organization ID (cross-org)    |
| `amount`                | number | Yes      | Payment amount (positive decimal)        |
| `currency`              | string | No       | ISO 4217 currency code (default: USD)    |
| `tx_type`               | string | Yes      | Transaction type identifier              |
| `category`              | string | No       | Transaction category                     |
| `description`           | string | No       | Human-readable description               |
| `reference_id`          | string | No       | External reference (invoice, PO, etc.)   |
| `metadata`              | object | No       | Arbitrary key-value metadata             |
| `escrow_conditions`     | object | No       | Escrow release conditions (if escrow)    |

**Response (200 - Authorized):**

```json
{
  "transaction_id": "txn_9f8e7d6c5b4a",
  "status": "authorized",
  "authorization": {
    "decision": "approved",
    "reason_code": "policy_pass",
    "compliance_status": "clear",
    "processing_time_ms": 342
  },
  "settlement": {
    "settled_at": "2026-04-14T12:35:00.000Z"
  }
}
```

**Response (200 - Denied):**

```json
{
  "transaction_id": "txn_9f8e7d6c5b4a",
  "status": "denied",
  "authorization": {
    "decision": "denied",
    "reason_code": "daily_limit_exceeded",
    "reason_detail": "Daily spending limit of $50,000 exceeded",
    "processing_time_ms": 89
  }
}
```

**Error Responses:**
- `400` - Missing required fields
- `403` - Missing `payments:request` permission

**curl Example:**

```bash
curl -X POST https://your-instance.pulse.app/pulse-api/payments/request \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "requesting_agent_id": "agent-treasury-ops",
    "counterparty_agent_id": "agent-vendor-pay",
    "amount": 2500.00,
    "currency": "USD",
    "tx_type": "vendor_payment",
    "category": "operations",
    "description": "Invoice INV-2026-0412",
    "reference_id": "INV-2026-0412"
  }'
```

---

### 2. GET /pulse-api/payments

List payment transactions with filtering and pagination.

**Permission:** `payments:read`

**Query Parameters:**

| Param      | Type   | Default | Description                              |
| ---------- | ------ | ------- | ---------------------------------------- |
| `limit`    | int    | 50      | Results per page (max 200)               |
| `offset`   | int    | 0       | Pagination offset                        |
| `status`   | string | -       | Filter by status                         |
| `tx_type`  | string | -       | Filter by transaction type               |
| `agent_id` | string | -       | Filter by agent (sender or receiver)     |
| `date_from`| string | -       | ISO 8601 start date filter               |
| `date_to`  | string | -       | ISO 8601 end date filter                 |

**Response (200):**

```json
{
  "transactions": [
    {
      "id": "txn_9f8e7d6c5b4a",
      "requesting_agent_id": "agent-treasury-ops",
      "requesting_org_id": "org_abc123",
      "counterparty_agent_id": "agent-vendor-pay",
      "counterparty_org_id": null,
      "amount": 2500.00,
      "currency": "USD",
      "tx_type": "vendor_payment",
      "category": "operations",
      "description": "Invoice INV-2026-0412",
      "reference_id": "INV-2026-0412",
      "status": "settled",
      "settled_at": "2026-04-14T12:35:00.000Z",
      "created_at": "2026-04-14T12:34:57.000Z"
    }
  ],
  "count": 1,
  "limit": 50,
  "offset": 0
}
```

**curl Example:**

```bash
curl "https://your-instance.pulse.app/pulse-api/payments?status=settled&limit=20" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

### 3. GET /pulse-api/payments/:id

Retrieve full detail for a single transaction including authorization, events, and escrow.

**Permission:** `payments:read`

**Response (200):**

```json
{
  "transaction": {
    "id": "txn_9f8e7d6c5b4a",
    "requesting_agent_id": "agent-treasury-ops",
    "requesting_org_id": "org_abc123",
    "counterparty_agent_id": "agent-vendor-pay",
    "amount": 2500.00,
    "currency": "USD",
    "tx_type": "vendor_payment",
    "status": "settled",
    "metadata": {"invoice_id": "INV-2026-0412"},
    "created_at": "2026-04-14T12:34:57.000Z"
  },
  "authorization": {
    "id": "auth_x1y2z3",
    "decision": "approved",
    "reason_code": "policy_pass",
    "processing_time_ms": 342,
    "created_at": "2026-04-14T12:34:57.500Z"
  },
  "events": [
    {"id": "evt_1", "event_type": "authorized", "created_at": "2026-04-14T12:34:57.500Z"},
    {"id": "evt_2", "event_type": "settled", "created_at": "2026-04-14T12:35:00.000Z"}
  ],
  "escrow": null
}
```

**Error Responses:**
- `404` - Transaction not found

**curl Example:**

```bash
curl "https://your-instance.pulse.app/pulse-api/payments/txn_9f8e7d6c5b4a" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

### 4. GET /pulse-api/payments/:id/events

Retrieve the event history for a transaction in chronological order.

**Permission:** `payments:read`

**Response (200):**

```json
{
  "events": [
    {
      "id": "evt_a1b2c3",
      "event_type": "authorized",
      "event_data": {"decision": "approved", "reason_code": "policy_pass"},
      "created_at": "2026-04-14T12:34:57.500Z"
    },
    {
      "id": "evt_d4e5f6",
      "event_type": "settled",
      "event_data": {"settled_at": "2026-04-14T12:35:00.000Z"},
      "created_at": "2026-04-14T12:35:00.000Z"
    }
  ]
}
```

**curl Example:**

```bash
curl "https://your-instance.pulse.app/pulse-api/payments/txn_9f8e7d6c5b4a/events" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

### 5. POST /pulse-api/payments/:id/dispute

Raise a dispute on an escrowed transaction.

**Permission:** `payments:write`

**Request Body:**

| Field    | Type   | Required | Description               |
| -------- | ------ | -------- | ------------------------- |
| `reason` | string | No       | Dispute reason text       |

**Response (200):**

```json
{
  "disputed": true,
  "escrow_id": "esc_a1b2c3",
  "status": "disputed",
  "disputed_at": "2026-04-14T13:00:00.000Z"
}
```

**Error Responses:**
- `400` - Transaction has no escrow
- `404` - Transaction not found

**curl Example:**

```bash
curl -X POST "https://your-instance.pulse.app/pulse-api/payments/txn_9f8e7d6c5b4a/dispute" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Deliverables not met per SOW section 3.2"}'
```

---

### 6. GET /pulse-api/wallets

List all active wallets for the authenticated organization.

**Permission:** `wallets:read`

**Response (200):**

```json
{
  "wallets": [
    {
      "id": "wal_a1b2c3",
      "agent_id": "agent-treasury-ops",
      "currency": "USD",
      "available_balance": 50000.00,
      "held_balance": 5000.00,
      "lifetime_sent": 1250000.00,
      "lifetime_received": 1350000.00,
      "last_transaction_at": "2026-04-14T12:35:00.000Z",
      "is_active": true,
      "created_at": "2026-01-15T00:00:00.000Z"
    }
  ]
}
```

**curl Example:**

```bash
curl "https://your-instance.pulse.app/pulse-api/wallets" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

### 7. GET /pulse-api/wallets/:agent_id

Retrieve detailed wallet information for a specific agent.

**Permission:** `wallets:read`

**Response (200):**

```json
{
  "id": "wal_a1b2c3",
  "org_id": "org_abc123",
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

**Error Responses:**
- `404` - Wallet not found

**curl Example:**

```bash
curl "https://your-instance.pulse.app/pulse-api/wallets/agent-treasury-ops" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

### 8. POST /pulse-api/wallets/:agent_id/fund

Add funds to an agent's wallet.

**Permission:** `wallets:write`

**Request Body:**

| Field      | Type   | Required | Description                        |
| ---------- | ------ | -------- | ---------------------------------- |
| `amount`   | number | Yes      | Amount to add (must be positive)   |
| `currency` | string | No       | Currency code (default: USD)       |

**Response (200):**

```json
{
  "funded": true,
  "agent_id": "agent-treasury-ops",
  "amount": 10000.00,
  "new_balance": 60000.00
}
```

**Error Responses:**
- `400` - Invalid or non-positive amount
- `404` - Wallet not found

**curl Example:**

```bash
curl -X POST "https://your-instance.pulse.app/pulse-api/wallets/agent-treasury-ops/fund" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"amount": 10000, "currency": "USD"}'
```

---

### 9. POST /pulse-api/wallets/:agent_id/withdraw

Withdraw funds from an agent's wallet.

**Permission:** `wallets:write`

**Request Body:**

| Field      | Type   | Required | Description                            |
| ---------- | ------ | -------- | -------------------------------------- |
| `amount`   | number | Yes      | Amount to withdraw (must be positive)  |
| `currency` | string | No       | Currency code (default: USD)           |

**Response (200):**

```json
{
  "withdrawn": true,
  "agent_id": "agent-treasury-ops",
  "amount": 5000.00,
  "new_balance": 45000.00
}
```

**Error Responses:**
- `400` - Invalid amount or insufficient balance
- `404` - Wallet not found

**curl Example:**

```bash
curl -X POST "https://your-instance.pulse.app/pulse-api/wallets/agent-treasury-ops/withdraw" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"amount": 5000, "currency": "USD"}'
```

---

### 10. GET /pulse-api/policies

List all spending policies for the authenticated organization.

**Permission:** `policies:read`

**Response (200):**

```json
{
  "policies": [
    {
      "id": "pol_abc123",
      "org_id": "org_abc123",
      "policy_name": "Default Policy",
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
      "is_active": true,
      "created_at": "2026-01-15T00:00:00.000Z"
    }
  ]
}
```

**curl Example:**

```bash
curl "https://your-instance.pulse.app/pulse-api/policies" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

### 11. POST /pulse-api/policies

Create a new spending policy.

**Permission:** `policies:write`

**Request Body:**

| Field                       | Type     | Required | Description                               |
| --------------------------- | -------- | -------- | ----------------------------------------- |
| `policy_name`               | string   | Yes      | Human-readable policy name                |
| `agent_id`                  | string   | No       | Agent ID (null for org-wide default)      |
| `max_per_transaction`       | number   | No       | Max amount per single transaction         |
| `max_daily`                 | number   | No       | Max daily aggregate spend                 |
| `max_monthly`               | number   | No       | Max monthly aggregate spend               |
| `currency`                  | string   | No       | Currency code (default: USD)              |
| `require_human_above`       | number   | No       | Human approval threshold                  |
| `approved_counterparties`   | string[] | No       | Allowed counterparty agent IDs            |
| `blocked_counterparties`    | string[] | No       | Blocked counterparty agent IDs            |
| `allowed_categories`        | string[] | No       | Permitted transaction categories          |
| `compliance_precheck`       | boolean  | No       | Enable compliance check (default: true)   |
| `compliance_jurisdictions`  | string[] | No       | Jurisdictions for compliance evaluation   |

**Response (201):**

```json
{
  "id": "pol_new123",
  "org_id": "org_abc123",
  "policy_name": "Treasury Agent Policy",
  "agent_id": "agent-treasury-ops",
  "max_per_transaction": 50000.00,
  "max_daily": 200000.00,
  "max_monthly": 2000000.00,
  "currency": "USD",
  "require_human_above": 100000.00,
  "approved_counterparties": ["agent-vendor-pay"],
  "blocked_counterparties": [],
  "allowed_categories": ["treasury", "operations"],
  "compliance_precheck": true,
  "compliance_jurisdictions": ["US_FEDERAL", "US_STATE_NY"],
  "is_active": true,
  "created_at": "2026-04-14T13:00:00.000Z"
}
```

**Error Responses:**
- `400` - Missing policy_name
- `409` - Active policy already exists for this agent

**curl Example:**

```bash
curl -X POST "https://your-instance.pulse.app/pulse-api/policies" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "policy_name": "Treasury Agent Policy",
    "agent_id": "agent-treasury-ops",
    "max_per_transaction": 50000,
    "max_daily": 200000,
    "max_monthly": 2000000,
    "require_human_above": 100000,
    "allowed_categories": ["treasury", "operations"],
    "compliance_jurisdictions": ["US_FEDERAL", "US_STATE_NY"]
  }'
```

---

### 12. PATCH /pulse-api/policies/:id

Update an existing spending policy. Supports partial updates.

**Permission:** `policies:write`

**Request Body:** Any subset of the fields from POST /pulse-api/policies (except `policy_name` is optional here).

**Response (200):**

```json
{
  "updated": true
}
```

**Error Responses:**
- `404` - Policy not found

**curl Example:**

```bash
curl -X PATCH "https://your-instance.pulse.app/pulse-api/policies/pol_abc123" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"max_per_transaction": 75000, "max_daily": 300000}'
```

---

### 13. DELETE /pulse-api/policies/:id

Soft-delete a spending policy (sets `is_active` to false).

**Permission:** `policies:write`

**Response (200):**

```json
{
  "deleted": true,
  "soft": true
}
```

**Error Responses:**
- `404` - Policy not found

**curl Example:**

```bash
curl -X DELETE "https://your-instance.pulse.app/pulse-api/policies/pol_abc123" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

### 14. GET /pulse-api/reconciliation

List reconciliation reports with filtering and pagination.

**Permission:** `reconciliation:read`

**Query Parameters:**

| Param      | Type   | Default | Description                    |
| ---------- | ------ | ------- | ------------------------------ |
| `limit`    | int    | 20      | Results per page (max 100)     |
| `offset`   | int    | 0       | Pagination offset              |
| `date_from`| string | -       | Filter by period start date    |
| `date_to`  | string | -       | Filter by period end date      |

**Response (200):**

```json
{
  "reports": [
    {
      "id": "rec_a1b2c3",
      "report_period_start": "2026-04-01T00:00:00.000Z",
      "report_period_end": "2026-04-07T23:59:59.999Z",
      "total_transactions": 450,
      "matched_count": 447,
      "unmatched_count": 2,
      "discrepancy_count": 1,
      "total_volume": 125000.00,
      "status": "completed",
      "created_at": "2026-04-08T01:00:00.000Z"
    }
  ],
  "count": 1,
  "limit": 20,
  "offset": 0
}
```

**curl Example:**

```bash
curl "https://your-instance.pulse.app/pulse-api/reconciliation?date_from=2026-04-01" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

### 15. POST /pulse-api/reconciliation/trigger

Trigger an on-demand reconciliation audit for a specified period.

**Permission:** `reconciliation:trigger`

**Request Body:**

| Field          | Type   | Required | Description                      |
| -------------- | ------ | -------- | -------------------------------- |
| `period_start` | string | No       | ISO 8601 start of period         |
| `period_end`   | string | No       | ISO 8601 end of period           |

**Response (200):**

```json
{
  "triggered": true,
  "report_id": "rec_new456",
  "status": "processing",
  "period_start": "2026-04-08T00:00:00.000Z",
  "period_end": "2026-04-14T23:59:59.999Z"
}
```

**curl Example:**

```bash
curl -X POST "https://your-instance.pulse.app/pulse-api/reconciliation/trigger" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"period_start": "2026-04-08T00:00:00Z", "period_end": "2026-04-14T23:59:59Z"}'
```

---

## Platform Routes (15 Endpoints)

### 16. GET /pulse-api/health

Health check endpoint. No authentication required.

**Response (200):**

```json
{
  "status": "operational",
  "version": "4.17.0",
  "timestamp": "2026-04-14T12:00:00.000Z"
}
```

```bash
curl "https://your-instance.pulse.app/pulse-api/health"
```

---

### 17. GET /pulse-api/meta

Returns organization metadata, permissions, and API key info for the authenticated key.

**Permission:** Any valid API key.

```bash
curl "https://your-instance.pulse.app/pulse-api/meta" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

### 18. POST /pulse-api/data/push

Push up to 100 records of structured data to the platform.

**Permission:** `data:write`

**Request Body:** `{ "source": string, "data_type": string, "records": array }`

```bash
curl -X POST "https://your-instance.pulse.app/pulse-api/data/push" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"source": "erp", "data_type": "invoices", "records": [{"external_id": "INV-001", "data": {"amount": 5000}}]}'
```

---

### 19. POST /pulse-api/data/bulk

Push up to 1,000 records in batches of 100.

**Permission:** `data:write`

**Request Body:** Same schema as `/pulse-api/data/push` but allows up to 1,000 records.

```bash
curl -X POST "https://your-instance.pulse.app/pulse-api/data/bulk" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"source": "erp", "data_type": "invoices", "records": [...]}'
```

---

### 20. GET/POST /pulse-api/data/query

Query stored data with filtering and pagination.

**Permission:** `data:read`

**Query Parameters / Body:** `limit`, `offset`, `data_type`, `category`, `connector_slug`, `date_from`, `date_to`

```bash
curl "https://your-instance.pulse.app/pulse-api/data/query?data_type=invoices&limit=50" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

### 21. GET /pulse-api/data/summary

Returns a summary of stored data grouped by type and category.

**Permission:** `data:read`

```bash
curl "https://your-instance.pulse.app/pulse-api/data/summary" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

### 22. POST /pulse-api/agents/trigger

Trigger a Pulse Engines agent run with optional input parameters.

**Permission:** `agents:trigger`

**Request Body:** `{ "agent": string, "input": object, "priority": string, "callback_webhook": string }`

```bash
curl -X POST "https://your-instance.pulse.app/pulse-api/agents/trigger" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"agent": "market-analyzer", "input": {"region": "northeast"}, "priority": "high"}'
```

---

### 23. GET /pulse-api/agents/status/:run_id

Check the status of a specific agent run.

**Permission:** `agents:trigger`

```bash
curl "https://your-instance.pulse.app/pulse-api/agents/status/run_abc123" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

### 24. GET /pulse-api/agents/results

List recent agent run results with optional filtering.

**Permission:** `agents:trigger`

**Query Parameters:** `agent` (filter by agent ID), `limit` (max 100, default 20)

```bash
curl "https://your-instance.pulse.app/pulse-api/agents/results?agent=market-analyzer&limit=10" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

### 25. GET /pulse-api/reports/efficiency

Aggregate efficiency metrics across all agent runs.

**Permission:** `reports:read`

```bash
curl "https://your-instance.pulse.app/pulse-api/reports/efficiency" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

### 26. GET /pulse-api/reports/compliance

Recent compliance predictions and risk assessments.

**Permission:** `reports:read`

```bash
curl "https://your-instance.pulse.app/pulse-api/reports/compliance" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

### 27. GET /pulse-api/reports/financial

Financial data records for the authenticated organization.

**Permission:** `reports:read`

```bash
curl "https://your-instance.pulse.app/pulse-api/reports/financial" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

### 28. GET /pulse-api/webhooks

List all webhook endpoints for the organization.

**Permission:** `webhooks:manage`

```bash
curl "https://your-instance.pulse.app/pulse-api/webhooks" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

### 29. POST /pulse-api/webhooks

Register a new webhook endpoint with event subscriptions and signing secret.

**Permission:** `webhooks:manage`

**Request Body:** `{ "url": string, "description": string, "events": string[], "agent_filter": string[] }`

```bash
curl -X POST "https://your-instance.pulse.app/pulse-api/webhooks" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://your-app.com/pulse-api/hooks", "events": ["payment.authorized", "payment.settled"]}'
```

---

### 30. PATCH/DELETE /pulse-api/webhooks/:id + GET deliveries + POST test

Manage individual webhook endpoints.

**Permission:** `webhooks:manage`

**PATCH** - Update endpoint configuration:
```bash
curl -X PATCH "https://your-instance.pulse.app/pulse-api/webhooks/whk_abc123" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"status": "active", "events": ["payment.authorized"]}'
```

**DELETE** - Remove endpoint and all delivery history:
```bash
curl -X DELETE "https://your-instance.pulse.app/pulse-api/webhooks/whk_abc123" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

**GET /pulse-api/webhooks/:id/deliveries** - View delivery history:
```bash
curl "https://your-instance.pulse.app/pulse-api/webhooks/whk_abc123/deliveries?limit=50" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

**POST /pulse-api/webhooks/:id/test** - Send test delivery:
```bash
curl -X POST "https://your-instance.pulse.app/pulse-api/webhooks/whk_abc123/test" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

## Permission Reference

| Permission              | Routes                                                  |
| ----------------------- | ------------------------------------------------------- |
| `payments:request`      | POST /pulse-api/payments/request                        |
| `payments:read`         | GET /pulse-api/payments, GET /pulse-api/payments/:id, GET /pulse-api/payments/:id/events |
| `payments:write`        | POST /pulse-api/payments/:id/dispute                    |
| `wallets:read`          | GET /pulse-api/wallets, GET /pulse-api/wallets/:agent_id|
| `wallets:write`         | POST /pulse-api/wallets/:agent_id/fund, POST /pulse-api/wallets/:agent_id/withdraw |
| `policies:read`         | GET /pulse-api/policies                                 |
| `policies:write`        | POST /pulse-api/policies, PATCH /pulse-api/policies/:id, DELETE /pulse-api/policies/:id |
| `reconciliation:read`   | GET /pulse-api/reconciliation                           |
| `reconciliation:trigger`| POST /pulse-api/reconciliation/trigger                  |
| `data:read`             | GET /pulse-api/data/query, GET /pulse-api/data/summary  |
| `data:write`            | POST /pulse-api/data/push, POST /pulse-api/data/bulk    |
| `agents:trigger`        | POST /pulse-api/agents/trigger, GET /pulse-api/agents/status/:id, GET /pulse-api/agents/results |
| `reports:read`          | GET /pulse-api/reports/efficiency, GET /pulse-api/reports/compliance, GET /pulse-api/reports/financial |
| `webhooks:manage`       | All /pulse-api/webhooks endpoints                       |

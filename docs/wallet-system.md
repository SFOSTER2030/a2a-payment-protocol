# Wallet System

> A2A Payment Protocol -- Agent Wallets, Balance Management & Settlement

---

## 1. Overview

Every dollar in the system exists in exactly one place at all times. There is no moment -- not even during a database transaction -- where money is in two wallets simultaneously or in no wallet at all.

The wallet system provides the financial backbone for all Pulse Engine
transactions. Each wallet is a logically isolated ledger that tracks
available and held balances with strict invariants enforced at the
database transaction level.

Key principles:

- **One wallet per agent per currency per organisation**.
- **Dual-balance model**: `available` (spendable) and `held` (escrow-locked).
- **Atomic operations**: all balance mutations occur within database
  transactions to prevent race conditions.
- **Immutable audit trail**: every balance change produces a ledger entry.

---

## 2. Wallet Identity

Each wallet is uniquely identified by the tuple:

```
(agent_id, currency, org_id)
```

### 2.1 Wallet Schema

```json
{
  "wallet_id": "wal-a1-usd-acme-001",
  "agent_id": "agent:data-processor-05",
  "org_id": "org:acme-corp",
  "currency": "USD",
  "available": 4500.00,
  "held": 500.00,
  "lifetime_credits": 125000.00,
  "lifetime_debits": 120000.00,
  "status": "active",
  "created_at": "2026-01-15T08:00:00Z",
  "updated_at": "2026-04-14T10:30:00Z"
}
```

### 2.2 Storage Model

The wallet store enforces the following constraints:

- Each wallet is uniquely identified by the combination of `(agent_id, currency, org_id)`.
- `available` and `held` balances must be non-negative.
- `lifetime_credits` and `lifetime_debits` must be non-negative.
- Timestamps (`created_at`, `updated_at`) are maintained automatically.

---

## 3. Balance Model

### 3.1 Dual-Balance Structure

| Balance     | Description                                               |
|-------------|-----------------------------------------------------------|
| `available` | Funds the agent may spend immediately.                    |
| `held`      | Funds locked in escrow; not spendable until released.     |

### 3.2 Total Balance Invariant

The fundamental invariant that must hold at all times:

```
available + held = total
```

Where `total` is the net of all credits minus all debits that have not
been reversed. This invariant is enforced by the database constraints
and verified by the reconciliation auditor on every run.

### 3.3 Balance Visibility

```
GET /pulse-api/wallets/{wallet_id}
```

Response:

```json
{
  "wallet_id": "wal-a1-usd-acme-001",
  "available": 4500.00,
  "held": 500.00,
  "total": 5000.00,
  "currency": "USD",
  "status": "active"
}
```

The `total` field is computed (`available + held`) and not stored
separately, eliminating the possibility of drift.

---

## 4. Atomic Operations

All balance mutations are executed within serialisable database
transactions. The system uses `SELECT ... FOR UPDATE` to acquire row-level
locks before modifying balances.

### 4.1 Transaction Template

```
BEGIN TRANSACTION

  1. Acquire exclusive lock on the target wallet record.
  2. Read current available and held balances.
  3. Perform the balance mutation (credit, debit, hold, or release).
  4. Update the wallet record with new balances and timestamp.
  5. Append an immutable ledger entry recording the operation.

COMMIT TRANSACTION
```

### 4.2 Race Condition Prevention

- Row-level locking prevents concurrent mutations on the same wallet.
- If two transactions attempt to modify the same wallet simultaneously,
  the second blocks until the first commits or rolls back.
- Deadlock detection is handled by the database engine with automatic
  retry (up to 3 attempts with exponential backoff).

### 4.3 Idempotency

Every balance mutation carries a unique `idempotency_key`. If a duplicate
key is submitted, the system returns the original result without
re-executing the mutation.

Idempotency keys are stored with the associated wallet ID, the operation result, a creation timestamp, and an expiry time (default: 24 hours). Duplicate keys return the original result without re-executing the mutation.

---

## 5. Fund and Withdraw via API

### 5.1 Fund (Credit)

Add funds to an agent's available balance:

```
POST /pulse-api/wallets/{wallet_id}/fund
Authorization: Bearer {admin_or_treasury_token}
Content-Type: application/json

{
  "amount": 1000.00,
  "currency": "USD",
  "source": "treasury:main-pool",
  "reference": "funding-round-Q2-2026",
  "idempotency_key": "fund-20260414-001"
}
```

**Processing**:

```
Step 1  Validate amount > 0 and currency matches wallet.
Step 2  Acquire row lock on wallet.
Step 3  wallet.available += amount.
Step 4  wallet.lifetime_credits += amount.
Step 5  Insert ledger entry: type=credit, amount=+1000.00.
Step 6  Commit transaction.
Step 7  Emit wallet.funded event.
```

Response:

```json
{
  "wallet_id": "wal-a1-usd-acme-001",
  "new_available": 5500.00,
  "new_held": 500.00,
  "ledger_entry_id": "led-20260414-001"
}
```

### 5.2 Withdraw (Debit)

Remove funds from an agent's available balance:

```
POST /pulse-api/wallets/{wallet_id}/withdraw
Authorization: Bearer {admin_or_treasury_token}
Content-Type: application/json

{
  "amount": 500.00,
  "currency": "USD",
  "destination": "treasury:main-pool",
  "reference": "quarterly-rebalance",
  "idempotency_key": "withdraw-20260414-001"
}
```

**Processing**:

```
Step 1  Validate amount > 0 and currency matches wallet.
Step 2  Acquire row lock on wallet.
Step 3  Check wallet.available >= amount. If not, reject with INSUFFICIENT_FUNDS.
Step 4  wallet.available -= amount.
Step 5  wallet.lifetime_debits += amount.
Step 6  Insert ledger entry: type=debit, amount=-500.00.
Step 7  Commit transaction.
Step 8  Emit wallet.withdrawn event.
```

---

## 6. Balance Check in Authorisation Pipeline

The wallet balance check occurs at **step 7** of the payment authorisation
pipeline.

### 6.1 Pipeline Context

```
Step 1  Request validation (schema, required fields)
Step 2  Agent authentication (token verification)
Step 3  Agent authorisation (role and permission check)
Step 4  Spending policy evaluation (limits, counterparties, categories)
Step 5  Compliance pre-check (if enabled)
Step 6  Human approval (if required by policy)
Step 7  >>> WALLET BALANCE CHECK <<<
Step 8  Escrow hold (if escrow mode)
Step 9  Settlement execution
Step 10 Event emission and notification
```

### 6.2 Balance Check Logic

```python
def check_balance(wallet, payment_request):
    required = payment_request.amount

    if wallet.status != 'active':
        raise WalletInactiveError(wallet.wallet_id)

    if wallet.currency != payment_request.currency:
        raise CurrencyMismatchError(wallet.currency, payment_request.currency)

    if wallet.available < required:
        raise InsufficientFundsError(
            wallet_id=wallet.wallet_id,
            available=wallet.available,
            required=required,
            shortfall=required - wallet.available
        )

    return BalanceCheckResult(
        wallet_id=wallet.wallet_id,
        available_before=wallet.available,
        amount_requested=required,
        available_after=wallet.available - required,
        check_passed=True
    )
```

### 6.3 Balance Check Response (Failure)

```json
{
  "error": "INSUFFICIENT_FUNDS",
  "wallet_id": "wal-a1-usd-acme-001",
  "available": 200.00,
  "required": 500.00,
  "shortfall": 300.00
}
```

---

## 7. Held Balance Management During Escrow

When a payment uses escrow settlement, the wallet system moves funds
between `available` and `held` through three operations: hold, release,
and refund.

### 7.1 Hold (Available -> Held)

Triggered when an escrow is created:

```
Step 1  Acquire row lock on payer wallet.
Step 2  Verify available >= escrow_amount.
Step 3  wallet.available -= escrow_amount.
Step 4  wallet.held += escrow_amount.
Step 5  Insert ledger entry: type=escrow_hold, amount=escrow_amount.
Step 6  Commit.
Step 7  Emit wallet.escrow_held event.
```

**Invariant check**: `available + held` remains unchanged.

### 7.2 Release (Held -> Payee Available)

Triggered when escrow transitions to Released:

```
Step 1  Acquire row lock on payer wallet.
Step 2  Verify payer wallet.held >= escrow_amount.
Step 3  payer_wallet.held -= escrow_amount.
Step 4  payer_wallet.lifetime_debits += escrow_amount.
Step 5  Insert payer ledger entry: type=escrow_release_debit.
Step 6  Acquire row lock on payee wallet.
Step 7  payee_wallet.available += escrow_amount.
Step 8  payee_wallet.lifetime_credits += escrow_amount.
Step 9  Insert payee ledger entry: type=escrow_release_credit.
Step 10 Commit (both wallets in same transaction).
Step 11 Emit wallet.escrow_released event.
```

Both wallet updates are in the **same database transaction** to ensure
atomicity. If either update fails, the entire operation rolls back.

### 7.3 Refund (Held -> Payer Available)

Triggered when escrow transitions to Refunded (via expiry or dispute):

```
Step 1  Acquire row lock on payer wallet.
Step 2  Verify payer wallet.held >= escrow_amount.
Step 3  payer_wallet.held -= escrow_amount.
Step 4  payer_wallet.available += escrow_amount.
Step 5  Insert ledger entry: type=escrow_refund.
Step 6  Commit.
Step 7  Emit wallet.escrow_refunded event.
```

**Invariant check**: `available + held` remains unchanged (funds move
within the same wallet).

---

## 8. Lifetime Totals

Lifetime totals provide aggregate metrics for each wallet. They are
**monotonically increasing** counters that only increment on final
settlement -- never on holds, pending states, or intermediate steps.

### 8.1 When Totals Increment

| Event                     | lifetime_credits | lifetime_debits |
|---------------------------|-----------------|-----------------|
| Fund (external credit)    | += amount       | --              |
| Withdraw (external debit) | --              | += amount       |
| Escrow hold               | --              | --              |
| Escrow release (payer)    | --              | += amount       |
| Escrow release (payee)    | += amount       | --              |
| Escrow refund             | --              | --              |
| Direct payment (payer)    | --              | += amount       |
| Direct payment (payee)    | += amount       | --              |

Note: escrow hold and refund do **not** affect lifetime totals because
they are intermediate operations. Only final settlement counts.

### 8.2 Lifetime Total Queries

```
GET /pulse-api/wallets/{wallet_id}/lifetime
```

Response:

```json
{
  "wallet_id": "wal-a1-usd-acme-001",
  "lifetime_credits": 125000.00,
  "lifetime_debits": 120000.00,
  "net_lifetime": 5000.00,
  "first_transaction_at": "2026-01-15T08:30:00Z",
  "last_transaction_at": "2026-04-14T10:30:00Z"
}
```

---

## 9. Multi-Currency

### 9.1 Wallet Per Currency

An agent operating in multiple currencies has a separate wallet for each:

```
agent:data-processor-05 @ org:acme-corp
  |-- wal-a1-usd-acme-001  (USD)
  |-- wal-a1-eur-acme-002  (EUR)
  |-- wal-a1-aed-acme-003  (AED)
```

### 9.2 Currency Isolation

Wallets of different currencies are completely independent. There is no
implicit conversion. A payment in EUR can only be funded from an EUR wallet.

### 9.3 Cross-Currency Payments

If an agent needs to pay in a currency it does not hold, the payment must
be routed through a currency exchange agent:

```
Step 1  Payer agent requests exchange from agent:fx-engine-01.
Step 2  FX engine debits payer's USD wallet.
Step 3  FX engine credits payer's EUR wallet at the agreed rate.
Step 4  Payer completes EUR payment from EUR wallet.
```

The exchange itself is a separate payment transaction with its own
authorisation and escrow lifecycle.

### 9.4 Supported Currencies

| Code | Currency              | Decimal Places |
|------|-----------------------|----------------|
| USD  | US Dollar             | 2              |
| EUR  | Euro                  | 2              |
| GBP  | British Pound         | 2              |
| AED  | UAE Dirham            | 2              |
| BRL  | Brazilian Real        | 2              |
| MXN  | Mexican Peso          | 2              |
| COP  | Colombian Peso        | 2              |

Additional currencies are added via configuration without schema changes.

---

## 10. Wallet Deactivation

### 10.1 Deactivation States

| Status       | Description                                              |
|--------------|----------------------------------------------------------|
| `active`     | Wallet is fully operational.                             |
| `suspended`  | Wallet cannot initiate payments; can receive refunds.    |
| `deactivated`| Wallet is frozen; no operations permitted.               |

### 10.2 Deactivation Flow

```
POST /pulse-api/wallets/{wallet_id}/deactivate
Authorization: Bearer {admin_token}
Body: {
  "reason": "Agent decommissioned",
  "admin_id": "admin:ops-lead-01"
}
```

**Processing**:

```
Step 1  Check no active escrows reference this wallet.
        If active escrows exist, reject with WALLET_HAS_ACTIVE_ESCROWS.
Step 2  Check held balance is 0.
        If held > 0, reject with WALLET_HAS_HELD_FUNDS.
Step 3  Set wallet.status = 'deactivated'.
Step 4  Insert audit log entry.
Step 5  Emit wallet.deactivated event.
Step 6  Notify agent and org admins.
```

### 10.3 Suspension vs Deactivation

Suspension is a softer restriction used during investigations:

```
POST /pulse-api/wallets/{wallet_id}/suspend
```

A suspended wallet:

- Cannot initiate new payments.
- Cannot be used as the funding source for new escrows.
- CAN receive refunds from existing escrows.
- CAN receive credits from admin funding operations.

### 10.4 Reactivation

```
POST /pulse-api/wallets/{wallet_id}/reactivate
Authorization: Bearer {admin_token}
Body: {
  "reason": "Investigation cleared",
  "admin_id": "admin:ops-lead-01"
}
```

Only `suspended` and `deactivated` wallets can be reactivated.

---

## 11. State Transitions for Each Settlement Mode

### 11.1 Direct Settlement (No Escrow)

```
Payer Wallet                        Payee Wallet
-----------                         ------------
available: 5000                     available: 1000
held:      0                        held:      0

  [Auth pipeline step 7: balance check passes]
  [Auth pipeline step 9: settlement execution]

available: 5000 - 500 = 4500       available: 1000 + 500 = 1500
held:      0                        held:      0
lifetime_debits += 500              lifetime_credits += 500
```

Ledger entries:

```
Payer: { type: "direct_debit",  amount: -500, ref: "pay-001" }
Payee: { type: "direct_credit", amount: +500, ref: "pay-001" }
```

### 11.2 Escrow Settlement -- Happy Path

```
Phase 1: Escrow Hold
  Payer Wallet
  available: 5000 -> 4500
  held:      0    -> 500

Phase 2: Escrow Release (all conditions met)
  Payer Wallet                      Payee Wallet
  available: 4500 (unchanged)       available: 1000 -> 1500
  held:      500  -> 0              held:      0 (unchanged)
  lifetime_debits += 500            lifetime_credits += 500
```

Ledger entries:

```
Phase 1 - Payer: { type: "escrow_hold", amount: 500, escrow: "esc-001" }
Phase 2 - Payer: { type: "escrow_release_debit", amount: -500, escrow: "esc-001" }
Phase 2 - Payee: { type: "escrow_release_credit", amount: +500, escrow: "esc-001" }
```

### 11.3 Escrow Settlement -- Refund Path (Expiry or Dispute)

```
Phase 1: Escrow Hold
  Payer Wallet
  available: 5000 -> 4500
  held:      0    -> 500

Phase 2: Escrow Refund
  Payer Wallet
  available: 4500 -> 5000
  held:      500  -> 0
  (lifetime totals unchanged -- no final settlement occurred)
```

Ledger entries:

```
Phase 1 - Payer: { type: "escrow_hold", amount: 500, escrow: "esc-001" }
Phase 2 - Payer: { type: "escrow_refund", amount: 500, escrow: "esc-001" }
```

### 11.4 State Transition Summary

```
             Direct Settlement
             -----------------
  available ----(-amount)----> available (payee)

             Escrow Hold
             -----------
  available ----(-amount)----> held (same wallet)

             Escrow Release
             ---------------
  held --------(-amount)----> available (payee wallet)

             Escrow Refund
             -------------
  held --------(-amount)----> available (same wallet)

             Fund
             ----
  [external] -(+amount)-----> available

             Withdraw
             --------
  available ---(-amount)----> [external]
```

---

## 12. Ledger Entries

Every balance mutation produces an immutable ledger entry.

### 12.1 Ledger Entry Schema

```json
{
  "ledger_entry_id": "led-20260414-001",
  "wallet_id": "wal-a1-usd-acme-001",
  "entry_type": "escrow_hold",
  "amount": 500.00,
  "balance_after_available": 4500.00,
  "balance_after_held": 500.00,
  "reference_type": "escrow",
  "reference_id": "esc-001",
  "idempotency_key": "hold-esc-001",
  "created_at": "2026-04-14T10:30:00Z",
  "metadata": {}
}
```

### 12.2 Ledger Store

The ledger store records each entry with the following properties:

- **Unique entry ID** for each ledger record.
- **Wallet reference** linking the entry to the originating wallet.
- **Entry type** restricted to: `credit`, `debit`, `escrow_hold`, `escrow_release_debit`, `escrow_release_credit`, `escrow_refund`, `direct_debit`, `direct_credit`, `fund`, `withdraw`.
- **Amount**, **balance snapshots** (available and held after the operation), and **timestamps**.
- **Reference fields** (type and ID) linking to the originating payment, escrow, or funding operation.
- **Idempotency key** ensuring each mutation is recorded exactly once.
- Entries are indexed by wallet and by reference for efficient lookups.

---

## 13. API Reference

| Method | Endpoint                                    | Description                     |
|--------|---------------------------------------------|---------------------------------|
| GET    | `/pulse-api/wallets/{id}`                   | Get wallet details              |
| POST   | `/pulse-api/wallets`                        | Create a new wallet             |
| POST   | `/pulse-api/wallets/{id}/fund`              | Fund wallet (credit)            |
| POST   | `/pulse-api/wallets/{id}/withdraw`          | Withdraw from wallet (debit)    |
| GET    | `/pulse-api/wallets/{id}/ledger`            | List ledger entries             |
| GET    | `/pulse-api/wallets/{id}/lifetime`          | Get lifetime totals             |
| POST   | `/pulse-api/wallets/{id}/suspend`           | Suspend wallet                  |
| POST   | `/pulse-api/wallets/{id}/deactivate`        | Deactivate wallet               |
| POST   | `/pulse-api/wallets/{id}/reactivate`        | Reactivate wallet               |
| GET    | `/pulse-api/agents/{id}/wallets`            | List all wallets for an agent   |
| GET    | `/pulse-api/orgs/{id}/wallets`              | List all wallets for an org     |

---

## 14. Error Codes

| Code                          | HTTP | Description                                 |
|-------------------------------|------|---------------------------------------------|
| `INSUFFICIENT_FUNDS`          | 402  | Available balance < requested amount        |
| `WALLET_INACTIVE`             | 403  | Wallet is suspended or deactivated          |
| `WALLET_HAS_ACTIVE_ESCROWS`  | 409  | Cannot deactivate with active escrows       |
| `WALLET_HAS_HELD_FUNDS`      | 409  | Cannot deactivate with non-zero held balance|
| `CURRENCY_MISMATCH`          | 422  | Payment currency does not match wallet      |
| `DUPLICATE_WALLET`           | 409  | Wallet already exists for agent/currency/org|
| `IDEMPOTENCY_CONFLICT`       | 409  | Idempotency key reused with different params|

---

*End of Wallet System specification.*

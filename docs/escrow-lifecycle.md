# Escrow Lifecycle

> A2A Payment Protocol -- Escrow State Machine & Resolution Paths

---

## 1. Overview

The escrow subsystem provides trustless settlement between autonomous Pulse Engines
by holding funds in a neutral state until predefined release conditions are
satisfied. Every inter-agent payment that opts into escrow follows the
deterministic state machine documented below.

Key design principles:

- **Atomic all-or-nothing**: partial releases are never permitted.
- **Single-dispute rule**: once a dispute is resolved, the outcome is final.
- **No nesting**: escrow-on-escrow is prohibited; an escrow cannot fund another.
- **Post-expiry finality**: disputes cannot be opened after an escrow expires.

---

## 2. Escrow States

| State        | Code | Description                                                       |
|--------------|------|-------------------------------------------------------------------|
| **Held**     | `H`  | Funds locked; awaiting release condition fulfilment.              |
| **Released** | `R`  | Funds transferred to the payee; terminal state.                   |
| **Refunded** | `F`  | Funds returned to the payer; terminal state.                      |
| **Disputed** | `D`  | Active dispute; funds frozen pending resolution.                  |
| **Expired**  | `X`  | TTL exceeded without release or dispute; triggers auto-refund.    |

Terminal states: `Released`, `Refunded`.
Intermediate states: `Held`, `Disputed`, `Expired`.

---

## 3. State Transition Table

```
 From       | To         | Trigger                      | Guard
------------|------------|------------------------------|-------------------------------
 Held       | Released   | release_conditions met       | all conditions status=passed
 Held       | Disputed   | POST /pulse-api/escrow/dispute | caller is payer or payee
 Held       | Expired    | cron tick past expires_at    | no active dispute
 Disputed   | Released   | admin resolution: release    | admin role required
 Disputed   | Refunded   | admin resolution: refund     | admin role required
 Expired    | Refunded   | auto-refund job              | always (automatic)
```

Transitions that are explicitly **forbidden**:

- `Released` -> any state (terminal)
- `Refunded` -> any state (terminal)
- `Expired` -> `Disputed` (no dispute after expiry)
- `Disputed` -> `Disputed` (no re-dispute after resolution)
- `Disputed` -> `Expired` (dispute freezes the clock)

---

## 4. Release Conditions Schema

Each escrow record contains a `release_conditions` array. Every condition in the
array must reach `status: "passed"` before the escrow transitions to `Released`.

```json
{
  "release_conditions": [
    {
      "type": "agent_verification",
      "target": "agent:shipping-tracker-01",
      "status": "pending",
      "evaluated_at": null,
      "meta": {}
    },
    {
      "type": "delivery_confirmation",
      "target": "agent:logistics-engine-07",
      "status": "pending",
      "evaluated_at": null,
      "meta": {}
    }
  ]
}
```

### 4.1 Condition Types

| Type                    | Description                                                        |
|-------------------------|--------------------------------------------------------------------|
| `agent_verification`    | A designated Pulse Engine confirms task completion via callback.    |
| `manual_review`         | A human operator marks the condition as passed in the dashboard.   |
| `delivery_confirmation` | A logistics or fulfilment engine posts a delivery receipt.         |
| `quality_check`         | An inspection engine evaluates output quality and posts a score.   |

### 4.2 Condition Fields

| Field          | Type     | Required | Notes                                       |
|----------------|----------|----------|---------------------------------------------|
| `type`         | string   | yes      | One of the four types above.                |
| `target`       | string   | yes      | Agent URI or human operator ID.             |
| `status`       | enum     | yes      | `pending`, `passed`, `failed`.              |
| `evaluated_at` | datetime | no       | ISO-8601 timestamp of last evaluation.      |
| `meta`         | object   | no       | Arbitrary data from the evaluator.          |

### 4.3 Evaluation Rules

1. Conditions are evaluated independently and in parallel.
2. A single `failed` condition blocks release and emits an alert.
3. Failed conditions may be retried up to 3 times within the escrow TTL.
4. If all conditions reach `passed`, the system transitions to `Released`
   within the next evaluation cycle (runs every 60 seconds).

---

## 5. Verification Agent Flow

When `type = "agent_verification"`:

```
Step 1  Escrow created with condition targeting verification agent.
Step 2  System dispatches POST /pulse-api/agents/{agent_id}/verify
        Body: { escrow_id, task_reference, callback_url }
Step 3  Verification agent performs its inspection logic.
Step 4  Agent posts result to callback:
        POST /pulse-api/escrow/{escrow_id}/conditions/{idx}/result
        Body: { status: "passed" | "failed", evidence: {...} }
Step 5  Escrow engine updates the condition record.
Step 6  If all conditions passed -> transition to Released.
        If any condition failed -> alert emitted, retry or dispute path.
```

The callback URL is signed with an HMAC token scoped to the escrow ID.
Tokens expire when the escrow expires or reaches a terminal state.

---

## 6. Manual Verification

When `type = "manual_review"`:

```
Step 1  Escrow created; dashboard shows pending manual review item.
Step 2  Human operator inspects the deliverable or evidence.
Step 3  Operator clicks Approve or Reject in the review panel.
Step 4  System updates condition:
        PATCH /pulse-api/escrow/{escrow_id}/conditions/{idx}
        Body: { status: "passed" | "failed", reviewer_id, notes }
Step 5  Escrow engine re-evaluates all conditions.
Step 6  Proceeds as in step 6 above.
```

Manual reviews have a separate SLA timer. If the reviewer does not act within
the configured `manual_review_sla_minutes` (default: 1440, i.e. 24 hours),
the system escalates to the next reviewer in the chain.

---

## 7. Expiry Calculation

Every escrow must define exactly one of:

| Field              | Type     | Description                                       |
|--------------------|----------|---------------------------------------------------|
| `duration_minutes` | integer  | Relative TTL from escrow creation timestamp.      |
| `expires_at`       | datetime | Absolute ISO-8601 expiry timestamp.               |

### 7.1 Resolution Logic

```python
if duration_minutes is not None:
    effective_expires_at = created_at + timedelta(minutes=duration_minutes)
elif expires_at is not None:
    effective_expires_at = expires_at
else:
    raise ValidationError("Escrow must specify duration_minutes or expires_at")
```

### 7.2 Hourly Cron Job

The expiry cron runs every hour at minute 0:

```
0 * * * *   pulse-escrow-expiry-worker
```

Processing steps:

1. Query all escrows where `state = 'held'` and `effective_expires_at <= NOW()`.
2. For each result, verify no active dispute exists.
3. Transition state from `Held` to `Expired`.
4. Emit `escrow.expired` event to the event bus.
5. Trigger auto-refund (see section 8).

### 7.3 Clock Freeze During Dispute

If an escrow enters `Disputed` state, the expiry clock is frozen. The
`effective_expires_at` is extended by the duration of the dispute once
resolved, if the resolution is to return the escrow to `Held` (which only
happens if the admin determines neither release nor refund is appropriate
and orders a re-evaluation -- an exceptional case).

---

## 8. Auto-Refund Mechanics

When an escrow reaches `Expired`:

```
Step 1  Expiry cron sets state = 'expired'.
Step 2  Refund job picks up expired escrows (runs in same cron cycle).
Step 3  System initiates wallet credit:
        POST /pulse-api/wallets/{payer_wallet_id}/credit
        Body: { amount, currency, reference: escrow_id, reason: "escrow_expired" }
Step 4  Payer wallet.available += escrow.amount.
Step 5  Escrow state transitions from Expired to Refunded.
Step 6  Emit escrow.refunded event.
Step 7  Notify payer and payee agents via their registered webhooks.
```

Refund is idempotent: if the credit call fails, the job retries on the next
cron cycle. The escrow remains in `Expired` until the refund succeeds.

---

## 9. Dispute Resolution Path

### 9.1 Opening a Dispute

Either the payer or the payee may dispute an escrow while it is in `Held` state.

```
POST /pulse-api/escrow/{escrow_id}/dispute
Authorization: Bearer {agent_token}
Body: {
  "reason": "deliverable_not_received",
  "evidence": { ... },
  "requested_outcome": "refund"
}
```

Response: `200 OK` with updated escrow showing `state: "disputed"`.

### 9.2 Freeze Phase

Once disputed:

- All release condition evaluations are paused.
- The expiry clock is frozen.
- Both parties are notified via webhook.
- A dispute record is created with a unique `dispute_id`.

### 9.3 Escalation

The dispute is escalated to the admin review queue:

```
Step 1  Dispute record created with status = 'open'.
Step 2  Dispatcher routes alert to the Admin Review channel.
Step 3  Escalation SLA begins (configurable, default 48 hours).
Step 4  If SLA breaches, alert severity is raised to critical.
```

### 9.4 Admin Review

The admin reviews all evidence from both parties:

```
GET  /pulse-api/disputes/{dispute_id}
GET  /pulse-api/disputes/{dispute_id}/evidence
```

The admin then issues a resolution:

```
POST /pulse-api/disputes/{dispute_id}/resolve
Body: {
  "outcome": "release" | "refund",
  "notes": "Evidence confirms delivery was completed.",
  "admin_id": "admin:ops-lead-01"
}
```

### 9.5 Resolution Execution

| Outcome   | Action                                                         |
|-----------|----------------------------------------------------------------|
| `release` | Escrow transitions Disputed -> Released; payee wallet credited.|
| `refund`  | Escrow transitions Disputed -> Refunded; payer wallet credited.|

After resolution:

- Dispute record status set to `resolved`.
- Both parties notified with outcome details.
- Audit log entry created.
- No further disputes can be opened on this escrow.

---

## 10. Edge Cases

### 10.1 No Partial Release

Escrow is atomic. The full amount is either released to the payee or refunded
to the payer. There is no mechanism to split the escrow amount. If a partial
settlement is needed, the agents must negotiate outside escrow and create
separate payment records for the agreed portions.

### 10.2 No Re-Dispute After Resolution

Once an admin resolves a dispute, the escrow reaches a terminal state
(`Released` or `Refunded`). The system rejects any subsequent dispute
attempts with HTTP 409 Conflict:

```json
{
  "error": "escrow_terminal",
  "message": "Escrow has reached terminal state and cannot be disputed."
}
```

### 10.3 No Escrow-on-Escrow

An escrow cannot be funded by another escrow's held balance. The funding
source must be the payer agent's `available` wallet balance. Attempting to
create an escrow with a reference to another escrow as funding source returns
HTTP 422 Unprocessable Entity.

### 10.4 No Dispute After Expiry

Once an escrow transitions to `Expired`, the dispute window is closed.
The auto-refund process takes over. Attempting to dispute an expired escrow
returns HTTP 410 Gone:

```json
{
  "error": "escrow_expired",
  "message": "Escrow has expired. Auto-refund is in progress."
}
```

---

## 11. Event Timeline Examples

### 11.1 Happy Path: Held -> Released

```
T+0m    escrow.created          Escrow #E-1001 created, state=held, amount=500 USD
T+0m    escrow.condition.added  agent_verification targeting agent:qa-engine-03
T+0m    escrow.condition.added  delivery_confirmation targeting agent:fulfil-09
T+5m    escrow.condition.eval   agent:qa-engine-03 posts status=passed
T+12m   escrow.condition.eval   agent:fulfil-09 posts status=passed
T+12m   escrow.released         All conditions met; 500 USD credited to payee wallet
T+12m   escrow.notify.payer     Webhook sent to payer agent
T+12m   escrow.notify.payee     Webhook sent to payee agent
```

### 11.2 Expiry Path: Held -> Expired -> Refunded

```
T+0m    escrow.created          Escrow #E-1002 created, duration_minutes=60
T+30m   escrow.condition.eval   agent:qa-engine-03 posts status=failed (retry 1)
T+45m   escrow.condition.eval   agent:qa-engine-03 posts status=failed (retry 2)
T+55m   escrow.condition.eval   agent:qa-engine-03 posts status=failed (retry 3)
T+60m   escrow.expired          Cron detects TTL exceeded, state=expired
T+60m   escrow.refund.initiated Auto-refund job triggered
T+60m   escrow.refunded         Payer wallet credited, state=refunded
T+60m   escrow.notify.payer     Refund notification sent
T+60m   escrow.notify.payee     Expiry notification sent
```

### 11.3 Dispute Path: Held -> Disputed -> Refunded

```
T+0m    escrow.created          Escrow #E-1003 created, state=held
T+20m   escrow.disputed         Payer opens dispute, state=disputed
T+20m   escrow.clock.frozen     Expiry clock paused
T+20m   dispute.created         Dispute #D-501 opened, reason=deliverable_not_received
T+20m   dispute.escalated       Alert routed to admin review queue
T+36h   dispute.reviewed        Admin reviews evidence from both parties
T+36h   dispute.resolved        Outcome=refund, admin:ops-lead-01
T+36h   escrow.refunded         Payer wallet credited, state=refunded
T+36h   escrow.notify.payer     Resolution notification (refund)
T+36h   escrow.notify.payee     Resolution notification (refund)
```

### 11.4 Dispute Path: Held -> Disputed -> Released

```
T+0m    escrow.created          Escrow #E-1004 created, state=held
T+15m   escrow.disputed         Payee opens dispute (claims payer denying valid delivery)
T+15m   escrow.clock.frozen     Expiry clock paused
T+15m   dispute.created         Dispute #D-502 opened, reason=unjust_withholding
T+24h   dispute.reviewed        Admin reviews delivery evidence
T+24h   dispute.resolved        Outcome=release, admin:ops-lead-01
T+24h   escrow.released         Payee wallet credited, state=released
T+24h   escrow.notify.payer     Resolution notification (release)
T+24h   escrow.notify.payee     Resolution notification (release)
```

---

## 12. API Reference Summary

| Method | Endpoint                                              | Description                    |
|--------|-------------------------------------------------------|--------------------------------|
| POST   | `/pulse-api/escrow`                                   | Create new escrow              |
| GET    | `/pulse-api/escrow/{id}`                              | Retrieve escrow details        |
| POST   | `/pulse-api/escrow/{id}/conditions/{idx}/result`      | Post condition evaluation      |
| PATCH  | `/pulse-api/escrow/{id}/conditions/{idx}`             | Manual condition update        |
| POST   | `/pulse-api/escrow/{id}/dispute`                      | Open a dispute                 |
| GET    | `/pulse-api/disputes/{id}`                            | Retrieve dispute details       |
| GET    | `/pulse-api/disputes/{id}/evidence`                   | List dispute evidence          |
| POST   | `/pulse-api/disputes/{id}/resolve`                    | Resolve a dispute (admin)      |

---

## 13. Configuration Defaults

| Parameter                   | Default | Unit    | Description                          |
|-----------------------------|---------|---------|--------------------------------------|
| `escrow_eval_interval`      | 60      | seconds | Release condition evaluation cycle   |
| `expiry_cron_interval`      | 60      | minutes | Expiry check frequency               |
| `max_condition_retries`     | 3       | count   | Per-condition retry limit            |
| `manual_review_sla_minutes` | 1440    | minutes | SLA for human reviewer response      |
| `dispute_escalation_sla`    | 2880    | minutes | SLA before critical escalation       |
| `callback_hmac_algorithm`   | sha256  | --      | HMAC signing for callback URLs       |

---

## 14. FAQ: Why All-or-Nothing?

**Q: Why doesn't escrow support partial release?**

Because partial release turns a simple state machine into an accounting system. The moment you allow "release 60% now, hold 40% pending quality review," you need fractional held balances, multiple release events per escrow, and a reconciliation model that tracks which portion went where. Every additional state multiplies the surface area for race conditions -- see [escrow-race-conditions.md](escrow-race-conditions.md) for the full analysis of what goes wrong when two release-condition callbacks arrive within the same evaluation cycle.

The atomic model keeps the invariant trivial: an escrow is either fully held or fully resolved. The wallet system never has to answer "how much of this escrow is still locked?" because the answer is always "all of it" or "none of it."

**Q: What if the parties genuinely need a split payout?**

They negotiate the split off-chain (or via agent messaging) and create separate payment records for each agreed portion. Two payments of $300 and $200 are two independent authorization-pipeline runs, two independent escrows if needed, and two clean audit trails. This is more work upfront but dramatically simpler to audit, dispute, and reconcile after the fact.

**Q: Has this ever been reconsidered?**

Twice. Both times the implementation prototype introduced at least three new edge cases in the dispute resolution path alone, and the reconciliation auditor's matching algorithm had to be rewritten to handle fractional phantom payments. The complexity cost exceeded the convenience benefit by a wide margin. The design stays atomic.

---

*End of Escrow Lifecycle specification.*

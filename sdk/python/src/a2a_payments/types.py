"""Data types and enumerations for the A2A Pulse Payments SDK."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, List, Optional, TypeVar


# ---------------------------------------------------------------------------
# String enums
# ---------------------------------------------------------------------------

class TransactionStatus(str, Enum):
    """Lifecycle status of a payment transaction."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class EscrowStatus(str, Enum):
    """Status of funds held in escrow."""

    HELD = "held"
    RELEASED = "released"
    DISPUTED = "disputed"
    REFUNDED = "refunded"
    EXPIRED = "expired"


class ReasonCode(str, Enum):
    """Machine-readable reason codes attached to disputes and failures."""

    INSUFFICIENT_FUNDS = "insufficient_funds"
    POLICY_VIOLATION = "policy_violation"
    DUPLICATE_TRANSACTION = "duplicate_transaction"
    AGENT_TIMEOUT = "agent_timeout"
    INVALID_RECIPIENT = "invalid_recipient"
    FRAUD_SUSPECTED = "fraud_suspected"
    SERVICE_UNAVAILABLE = "service_unavailable"
    MANUAL_REVIEW = "manual_review"


class EventType(str, Enum):
    """Webhook / audit-log event types."""

    PAYMENT_CREATED = "payment.created"
    PAYMENT_PROCESSING = "payment.processing"
    PAYMENT_COMPLETED = "payment.completed"
    PAYMENT_FAILED = "payment.failed"
    PAYMENT_DISPUTED = "payment.disputed"
    ESCROW_HELD = "escrow.held"
    ESCROW_RELEASED = "escrow.released"
    WALLET_FUNDED = "wallet.funded"
    WALLET_WITHDRAWN = "wallet.withdrawn"
    POLICY_VIOLATED = "policy.violated"
    RECONCILIATION_COMPLETED = "reconciliation.completed"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PaymentRequest:
    """Payload sent when initiating a new payment."""

    from_agent_id: str
    to_agent_id: str
    amount: float
    currency: str = "USD"
    idempotency_key: Optional[str] = None
    memo: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


@dataclass
class Transaction:
    """Core ledger record for a single fund movement."""

    transaction_id: str
    from_agent_id: str
    to_agent_id: str
    amount: float
    currency: str
    status: TransactionStatus
    created_at: str
    updated_at: str
    memo: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


@dataclass
class PaymentResponse:
    """Full representation of a payment returned by the API."""

    payment_id: str
    from_agent_id: str
    to_agent_id: str
    amount: float
    currency: str
    status: TransactionStatus
    escrow_status: Optional[EscrowStatus]
    created_at: str
    updated_at: str
    transactions: List[Transaction] = field(default_factory=list)
    memo: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


@dataclass
class PaymentEvent:
    """An event in a payment's lifecycle (audit log entry)."""

    event_id: str
    payment_id: str
    event_type: EventType
    occurred_at: str
    actor: Optional[str] = None
    details: Optional[dict[str, Any]] = None


@dataclass
class Wallet:
    """Agent wallet with balances and limits."""

    wallet_id: str
    agent_id: str
    currency: str
    balance: float
    available_balance: float
    pending_balance: float
    created_at: str
    updated_at: str


@dataclass
class SpendingPolicy:
    """A spending policy governing agent transactions."""

    policy_id: str
    name: str
    agent_id: Optional[str]
    max_transaction_amount: Optional[float] = None
    daily_limit: Optional[float] = None
    monthly_limit: Optional[float] = None
    allowed_currencies: Optional[List[str]] = None
    allowed_recipients: Optional[List[str]] = None
    require_escrow: bool = False
    created_at: str = ""
    updated_at: str = ""


@dataclass
class ReconciliationReport:
    """Summary of a reconciliation run."""

    report_id: str
    status: str
    started_at: str
    completed_at: Optional[str]
    total_transactions: int
    matched: int
    unmatched: int
    discrepancies: List[dict[str, Any]] = field(default_factory=list)


T = TypeVar("T")


@dataclass
class PaginatedResponse(Generic[T]):
    """Wrapper for paginated list endpoints."""

    data: List[T]
    total: int
    page: int
    per_page: int
    has_more: bool


@dataclass
class WebhookPayload:
    """Deserialized webhook delivery body."""

    webhook_id: str
    event_type: EventType
    created_at: str
    data: dict[str, Any]

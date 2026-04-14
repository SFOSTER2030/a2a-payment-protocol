/* ------------------------------------------------------------------ */
/*  Pulse Payments A2A SDK - Type Definitions                         */
/* ------------------------------------------------------------------ */

/** Status of a transaction as it moves through the settlement pipeline. */
export enum TransactionStatus {
  Pending      = "pending",
  Authorized   = "authorized",
  Captured     = "captured",
  Settled      = "settled",
  Disputed     = "disputed",
  Refunded     = "refunded",
  Cancelled    = "cancelled",
  Failed       = "failed",
}

/** Categories of lifecycle events emitted for a payment. */
export enum EventType {
  Created          = "payment.created",
  Authorized       = "payment.authorized",
  Captured         = "payment.captured",
  Settled          = "payment.settled",
  Disputed         = "payment.disputed",
  DisputeResolved  = "payment.dispute_resolved",
  Refunded         = "payment.refunded",
  Cancelled        = "payment.cancelled",
  Failed           = "payment.failed",
  WalletFunded     = "wallet.funded",
  WalletWithdrawn  = "wallet.withdrawn",
  PolicyViolation  = "policy.violation",
}

/** Reason codes attached to disputes. */
export enum ReasonCode {
  Unauthorized         = "unauthorized",
  DuplicateCharge      = "duplicate_charge",
  ServiceNotRendered   = "service_not_rendered",
  AmountMismatch       = "amount_mismatch",
  FraudSuspected       = "fraud_suspected",
  Other                = "other",
}

/** Escrow lifecycle states. */
export enum EscrowStatus {
  Held      = "held",
  Released  = "released",
  Reversed  = "reversed",
}

/** Severity levels for reconciliation findings. */
export enum Severity {
  Info     = "info",
  Warning  = "warning",
  Error    = "error",
  Critical = "critical",
}

/* ------------------------------------------------------------------ */
/*  Request / Response Shapes                                         */
/* ------------------------------------------------------------------ */

/** Payload sent to create a new payment request. */
export interface PaymentRequest {
  /** Amount in the smallest currency unit (e.g. cents). */
  amount: number;
  /** ISO 4217 currency code. */
  currency: string;
  /** Wallet ID of the sending agent. */
  from_wallet_id: string;
  /** Wallet ID of the receiving agent. */
  to_wallet_id: string;
  /** Unique client-generated idempotency key. */
  idempotency_key?: string;
  /** Human-readable memo attached to the payment. */
  memo?: string;
  /** Arbitrary key-value metadata. */
  metadata?: Record<string, unknown>;
}

/** Full payment record returned by the API. */
export interface PaymentResponse {
  id: string;
  amount: number;
  currency: string;
  from_wallet_id: string;
  to_wallet_id: string;
  status: TransactionStatus;
  idempotency_key: string | null;
  memo: string | null;
  metadata: Record<string, unknown>;
  escrow_status: EscrowStatus | null;
  created_at: string;
  updated_at: string;
}

/** Legacy alias kept for backward compatibility. */
export type Transaction = PaymentResponse;

/** A single lifecycle event for a payment. */
export interface PaymentEvent {
  id: string;
  payment_id: string;
  type: EventType;
  data: Record<string, unknown>;
  created_at: string;
}

/** Agent wallet record. */
export interface Wallet {
  id: string;
  agent_id: string;
  label: string;
  currency: string;
  balance: number;
  available_balance: number;
  held_balance: number;
  created_at: string;
  updated_at: string;
}

/** Payload used to create a new spending policy. */
export interface PolicyCreate {
  name: string;
  wallet_id: string;
  /** Maximum single-transaction amount (smallest unit). */
  max_amount?: number;
  /** Maximum daily spend (smallest unit). */
  daily_limit?: number;
  /** Maximum monthly spend (smallest unit). */
  monthly_limit?: number;
  /** List of allowed destination wallet IDs. If empty, all destinations are allowed. */
  allowed_destinations?: string[];
  /** List of allowed currency codes. */
  allowed_currencies?: string[];
  /** Whether the policy is active. */
  enabled?: boolean;
  metadata?: Record<string, unknown>;
}

/** Full spending-policy record returned by the API. */
export interface SpendingPolicy {
  id: string;
  name: string;
  wallet_id: string;
  max_amount: number | null;
  daily_limit: number | null;
  monthly_limit: number | null;
  allowed_destinations: string[];
  allowed_currencies: string[];
  enabled: boolean;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

/** Reconciliation report record. */
export interface ReconciliationReport {
  id: string;
  status: "pending" | "running" | "completed" | "failed";
  severity: Severity;
  total_transactions: number;
  matched: number;
  mismatched: number;
  findings: ReconciliationFinding[];
  started_at: string;
  completed_at: string | null;
  created_at: string;
}

export interface ReconciliationFinding {
  payment_id: string;
  severity: Severity;
  message: string;
  expected: unknown;
  actual: unknown;
}

/* ------------------------------------------------------------------ */
/*  Generic Helpers                                                    */
/* ------------------------------------------------------------------ */

/** Shared query parameters for paginated list endpoints. */
export interface ListParams {
  /** 1-based page number. */
  page?: number;
  /** Items per page (max 100). */
  per_page?: number;
  /** Field name to sort by. */
  sort_by?: string;
  /** Sort direction. */
  sort_order?: "asc" | "desc";
  /** Filter: only records after this ISO timestamp. */
  created_after?: string;
  /** Filter: only records before this ISO timestamp. */
  created_before?: string;
}

/** Envelope returned by every paginated list endpoint. */
export interface PaginatedResponse<T> {
  data: T[];
  page: number;
  per_page: number;
  total: number;
  total_pages: number;
}

/** Incoming webhook event payload. */
export interface WebhookPayload {
  id: string;
  type: EventType;
  created_at: string;
  data: Record<string, unknown>;
}

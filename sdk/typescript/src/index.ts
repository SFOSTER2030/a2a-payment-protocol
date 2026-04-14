/* ------------------------------------------------------------------ */
/*  Pulse Payments A2A SDK - Public API Surface                       */
/* ------------------------------------------------------------------ */

export { PulsePayments } from "./client.js";
export type { PulsePaymentsConfig } from "./client.js";

export {
  TransactionStatus,
  EventType,
  ReasonCode,
  EscrowStatus,
  Severity,
} from "./types.js";

export type {
  PaymentRequest,
  PaymentResponse,
  Transaction,
  PaymentEvent,
  Wallet,
  PolicyCreate,
  SpendingPolicy,
  ReconciliationReport,
  ReconciliationFinding,
  ListParams,
  PaginatedResponse,
  WebhookPayload,
} from "./types.js";

export {
  PulseApiError,
  AuthenticationError,
  RateLimitError,
  NotFoundError,
  ConflictError,
} from "./errors.js";

export { verifyWebhookSignature } from "./webhook.js";

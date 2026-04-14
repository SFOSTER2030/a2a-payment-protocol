/* ------------------------------------------------------------------ */
/*  Pulse Payments A2A SDK - Error Classes                            */
/* ------------------------------------------------------------------ */

/**
 * Base error for every non-OK response from the Pulse API.
 *
 * Carries the HTTP `status` code and an optional machine-readable
 * `code` string returned by the server.
 */
export class PulseApiError extends Error {
  /** HTTP status code (e.g. 400, 500). */
  public readonly status: number;
  /** Machine-readable error code from the API body, if present. */
  public readonly code: string | undefined;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "PulseApiError";
    this.status = status;
    this.code = code;

    // Maintain correct prototype chain in transpiled output.
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/** Thrown when the API key is missing, invalid, or revoked (HTTP 401). */
export class AuthenticationError extends PulseApiError {
  constructor(message = "Invalid or missing API key") {
    super(message, 401, "authentication_error");
    this.name = "AuthenticationError";
  }
}

/** Thrown when the caller exceeds the rate limit (HTTP 429). */
export class RateLimitError extends PulseApiError {
  /** Seconds to wait before retrying, if the server provided Retry-After. */
  public readonly retryAfter: number | undefined;

  constructor(message = "Rate limit exceeded", retryAfter?: number) {
    super(message, 429, "rate_limit_exceeded");
    this.name = "RateLimitError";
    this.retryAfter = retryAfter;
  }
}

/** Thrown when the requested resource does not exist (HTTP 404). */
export class NotFoundError extends PulseApiError {
  constructor(message = "Resource not found") {
    super(message, 404, "not_found");
    this.name = "NotFoundError";
  }
}

/** Thrown on idempotency or state-transition conflicts (HTTP 409). */
export class ConflictError extends PulseApiError {
  constructor(message = "Conflict: resource already exists or state transition invalid") {
    super(message, 409, "conflict");
    this.name = "ConflictError";
  }
}

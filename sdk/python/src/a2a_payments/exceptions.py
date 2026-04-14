"""Exception types for the A2A Pulse Payments SDK."""

from __future__ import annotations


class PulseApiError(Exception):
    """Base exception for all Pulse API errors.

    Attributes:
        status: HTTP status code returned by the API.
        code: Machine-readable error code (e.g. ``"INSUFFICIENT_FUNDS"``).
        message: Human-readable description of the error.
    """

    def __init__(self, status: int, code: str, message: str) -> None:
        self.status = status
        self.code = code
        self.message = message
        super().__init__(f"[{status}] {code}: {message}")


class AuthenticationError(PulseApiError):
    """Raised when the API key is missing, invalid, or expired (HTTP 401)."""

    def __init__(self, message: str = "Invalid or missing API key") -> None:
        super().__init__(status=401, code="AUTHENTICATION_FAILED", message=message)


class RateLimitError(PulseApiError):
    """Raised when the request is throttled (HTTP 429).

    Attributes:
        retry_after: Seconds to wait before retrying, if provided by the API.
    """

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: float | None = None,
    ) -> None:
        self.retry_after = retry_after
        super().__init__(status=429, code="RATE_LIMITED", message=message)


class NotFoundError(PulseApiError):
    """Raised when the requested resource does not exist (HTTP 404)."""

    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(status=404, code="NOT_FOUND", message=message)


class ConflictError(PulseApiError):
    """Raised on idempotency or state conflicts (HTTP 409)."""

    def __init__(self, message: str = "Request conflicts with current state") -> None:
        super().__init__(status=409, code="CONFLICT", message=message)

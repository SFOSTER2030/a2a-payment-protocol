"""Webhook signature verification for the A2A Pulse Payments SDK."""

from __future__ import annotations

import hashlib
import hmac


def verify_webhook(
    payload: bytes | str,
    signature: str,
    secret: str,
) -> bool:
    """Verify the HMAC-SHA256 signature of an incoming webhook payload.

    Args:
        payload: Raw request body bytes (or string, which will be UTF-8 encoded).
        signature: The ``X-Pulse-Signature`` header value sent with the webhook.
        secret: Your webhook signing secret from the dashboard.

    Returns:
        ``True`` if the signature is valid, ``False`` otherwise.

    Example::

        from a2a_payments import verify_webhook

        is_valid = verify_webhook(
            payload=request.body,
            signature=request.headers["X-Pulse-Signature"],
            secret="your_webhook_secret",
        )
        if not is_valid:
            raise ValueError("Invalid webhook signature")
    """
    if isinstance(payload, str):
        payload = payload.encode("utf-8")

    expected = hmac.new(
        key=secret.encode("utf-8"),
        msg=payload,
        digestmod=hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)

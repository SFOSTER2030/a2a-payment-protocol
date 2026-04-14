"""Synchronous HTTP client for the A2A Pulse Payments API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from .exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PulseApiError,
    RateLimitError,
)
from .types import (
    PaginatedResponse,
    PaymentEvent,
    PaymentRequest,
    PaymentResponse,
    ReconciliationReport,
    SpendingPolicy,
    Transaction,
    TransactionStatus,
    EscrowStatus,
    EventType,
    Wallet,
)


_DEFAULT_BASE_URL = "https://{your-instance}.pulse-internal/api"


class PulsePayments:
    """Client for the A2A Pulse Payments API.

    Args:
        api_key: Bearer token used to authenticate every request.
        base_url: Override the default API base URL.
        timeout: Request timeout in seconds (default ``30``).

    Example::

        from a2a_payments import PulsePayments

        client = PulsePayments(api_key="YOUR_API_KEY)
        payment = client.request_payment(
            from_agent_id="agent_sender",
            to_agent_id="agent_receiver",
            amount=25.00,
        )
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=timeout,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Send an authenticated request and return parsed JSON.

        Raises:
            AuthenticationError: On 401 responses.
            NotFoundError: On 404 responses.
            ConflictError: On 409 responses.
            RateLimitError: On 429 responses.
            PulseApiError: On any other non-2xx response.
        """
        response = self._client.request(method, path, json=json, params=params)

        if response.status_code >= 400:
            self._raise_for_status(response)

        if response.status_code == 204:
            return None

        return response.json()

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        """Map HTTP error responses to typed exceptions."""
        try:
            body = response.json()
        except Exception:
            body = {}

        code = body.get("code", "UNKNOWN")
        message = body.get("message", response.text or "Unknown error")
        status = response.status_code

        if status == 401:
            raise AuthenticationError(message)
        if status == 404:
            raise NotFoundError(message)
        if status == 409:
            raise ConflictError(message)
        if status == 429:
            retry_after_hdr = response.headers.get("Retry-After")
            retry_after = float(retry_after_hdr) if retry_after_hdr else None
            raise RateLimitError(message, retry_after=retry_after)

        raise PulseApiError(status=status, code=code, message=message)

    # ------------------------------------------------------------------
    # Payments
    # ------------------------------------------------------------------

    def request_payment(
        self,
        from_agent_id: str,
        to_agent_id: str,
        amount: float,
        currency: str = "USD",
        *,
        idempotency_key: Optional[str] = None,
        memo: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PaymentResponse:
        """Initiate a new agent-to-agent payment.

        Args:
            from_agent_id: Sending agent identifier.
            to_agent_id: Receiving agent identifier.
            amount: Payment amount (positive number).
            currency: ISO 4217 currency code.
            idempotency_key: Optional key to prevent duplicate payments.
            memo: Human-readable note attached to the payment.
            metadata: Arbitrary key-value pairs stored with the payment.

        Returns:
            The created payment.
        """
        payload: Dict[str, Any] = {
            "from_agent_id": from_agent_id,
            "to_agent_id": to_agent_id,
            "amount": amount,
            "currency": currency,
        }
        if idempotency_key is not None:
            payload["idempotency_key"] = idempotency_key
        if memo is not None:
            payload["memo"] = memo
        if metadata is not None:
            payload["metadata"] = metadata

        data = self._request("POST", "/payments", json=payload)
        return self._parse_payment(data)

    def get_payment(self, payment_id: str) -> PaymentResponse:
        """Retrieve a single payment by ID.

        Args:
            payment_id: The payment identifier.

        Returns:
            The payment record.
        """
        data = self._request("GET", f"/payments/{payment_id}")
        return self._parse_payment(data)

    def list_payments(
        self,
        *,
        agent_id: Optional[str] = None,
        status: Optional[TransactionStatus] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> PaginatedResponse[PaymentResponse]:
        """List payments with optional filters.

        Args:
            agent_id: Filter by sender or receiver agent ID.
            status: Filter by transaction status.
            page: Page number (1-indexed).
            per_page: Results per page (max 100).

        Returns:
            Paginated list of payments.
        """
        params: Dict[str, Any] = {"page": page, "per_page": per_page}
        if agent_id is not None:
            params["agent_id"] = agent_id
        if status is not None:
            params["status"] = status.value

        data = self._request("GET", "/payments", params=params)
        return PaginatedResponse(
            data=[self._parse_payment(p) for p in data["data"]],
            total=data["total"],
            page=data["page"],
            per_page=data["per_page"],
            has_more=data["has_more"],
        )

    def get_payment_events(self, payment_id: str) -> List[PaymentEvent]:
        """Retrieve the audit-log events for a payment.

        Args:
            payment_id: The payment identifier.

        Returns:
            Ordered list of events.
        """
        data = self._request("GET", f"/payments/{payment_id}/events")
        return [
            PaymentEvent(
                event_id=e["event_id"],
                payment_id=e["payment_id"],
                event_type=EventType(e["event_type"]),
                occurred_at=e["occurred_at"],
                actor=e.get("actor"),
                details=e.get("details"),
            )
            for e in data
        ]

    def dispute_payment(
        self,
        payment_id: str,
        reason: str,
        *,
        reason_code: Optional[str] = None,
    ) -> PaymentResponse:
        """Open a dispute on an existing payment.

        Args:
            payment_id: The payment to dispute.
            reason: Free-text explanation of the dispute.
            reason_code: Optional machine-readable reason code.

        Returns:
            The updated payment with dispute status.
        """
        payload: Dict[str, Any] = {"reason": reason}
        if reason_code is not None:
            payload["reason_code"] = reason_code

        data = self._request("POST", f"/payments/{payment_id}/dispute", json=payload)
        return self._parse_payment(data)

    # ------------------------------------------------------------------
    # Wallets
    # ------------------------------------------------------------------

    def get_wallet(self, wallet_id: str) -> Wallet:
        """Retrieve a wallet by ID.

        Args:
            wallet_id: The wallet identifier.

        Returns:
            Wallet details including balances.
        """
        data = self._request("GET", f"/wallets/{wallet_id}")
        return self._parse_wallet(data)

    def list_wallets(
        self,
        *,
        agent_id: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> PaginatedResponse[Wallet]:
        """List wallets with optional agent filter.

        Args:
            agent_id: Filter to wallets owned by this agent.
            page: Page number (1-indexed).
            per_page: Results per page (max 100).

        Returns:
            Paginated list of wallets.
        """
        params: Dict[str, Any] = {"page": page, "per_page": per_page}
        if agent_id is not None:
            params["agent_id"] = agent_id

        data = self._request("GET", "/wallets", params=params)
        return PaginatedResponse(
            data=[self._parse_wallet(w) for w in data["data"]],
            total=data["total"],
            page=data["page"],
            per_page=data["per_page"],
            has_more=data["has_more"],
        )

    def fund_wallet(
        self,
        wallet_id: str,
        amount: float,
        *,
        idempotency_key: Optional[str] = None,
    ) -> Wallet:
        """Add funds to a wallet.

        Args:
            wallet_id: The wallet to fund.
            amount: Amount to add (positive number).
            idempotency_key: Optional deduplication key.

        Returns:
            Updated wallet with new balances.
        """
        payload: Dict[str, Any] = {"amount": amount}
        if idempotency_key is not None:
            payload["idempotency_key"] = idempotency_key

        data = self._request("POST", f"/wallets/{wallet_id}/fund", json=payload)
        return self._parse_wallet(data)

    def withdraw_wallet(
        self,
        wallet_id: str,
        amount: float,
        *,
        idempotency_key: Optional[str] = None,
    ) -> Wallet:
        """Withdraw funds from a wallet.

        Args:
            wallet_id: The wallet to withdraw from.
            amount: Amount to withdraw (positive number).
            idempotency_key: Optional deduplication key.

        Returns:
            Updated wallet with new balances.
        """
        payload: Dict[str, Any] = {"amount": amount}
        if idempotency_key is not None:
            payload["idempotency_key"] = idempotency_key

        data = self._request("POST", f"/wallets/{wallet_id}/withdraw", json=payload)
        return self._parse_wallet(data)

    # ------------------------------------------------------------------
    # Spending policies
    # ------------------------------------------------------------------

    def create_policy(
        self,
        name: str,
        *,
        agent_id: Optional[str] = None,
        max_transaction_amount: Optional[float] = None,
        daily_limit: Optional[float] = None,
        monthly_limit: Optional[float] = None,
        allowed_currencies: Optional[List[str]] = None,
        allowed_recipients: Optional[List[str]] = None,
        require_escrow: bool = False,
    ) -> SpendingPolicy:
        """Create a new spending policy.

        Args:
            name: Display name for the policy.
            agent_id: Scope the policy to a specific agent (or ``None`` for global).
            max_transaction_amount: Per-transaction cap.
            daily_limit: Rolling 24-hour spend limit.
            monthly_limit: Calendar-month spend limit.
            allowed_currencies: Whitelist of ISO 4217 codes.
            allowed_recipients: Whitelist of recipient agent IDs.
            require_escrow: If ``True``, all matching payments go through escrow.

        Returns:
            The created policy.
        """
        payload: Dict[str, Any] = {"name": name, "require_escrow": require_escrow}
        if agent_id is not None:
            payload["agent_id"] = agent_id
        if max_transaction_amount is not None:
            payload["max_transaction_amount"] = max_transaction_amount
        if daily_limit is not None:
            payload["daily_limit"] = daily_limit
        if monthly_limit is not None:
            payload["monthly_limit"] = monthly_limit
        if allowed_currencies is not None:
            payload["allowed_currencies"] = allowed_currencies
        if allowed_recipients is not None:
            payload["allowed_recipients"] = allowed_recipients

        data = self._request("POST", "/policies", json=payload)
        return self._parse_policy(data)

    def list_policies(
        self,
        *,
        agent_id: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> PaginatedResponse[SpendingPolicy]:
        """List spending policies.

        Args:
            agent_id: Filter by owning agent.
            page: Page number (1-indexed).
            per_page: Results per page (max 100).

        Returns:
            Paginated list of policies.
        """
        params: Dict[str, Any] = {"page": page, "per_page": per_page}
        if agent_id is not None:
            params["agent_id"] = agent_id

        data = self._request("GET", "/policies", params=params)
        return PaginatedResponse(
            data=[self._parse_policy(p) for p in data["data"]],
            total=data["total"],
            page=data["page"],
            per_page=data["per_page"],
            has_more=data["has_more"],
        )

    def update_policy(
        self,
        policy_id: str,
        **kwargs: Any,
    ) -> SpendingPolicy:
        """Update an existing spending policy.

        Args:
            policy_id: The policy to update.
            **kwargs: Fields to update (same as ``create_policy`` arguments).

        Returns:
            The updated policy.
        """
        data = self._request("PATCH", f"/policies/{policy_id}", json=kwargs)
        return self._parse_policy(data)

    def delete_policy(self, policy_id: str) -> None:
        """Delete a spending policy.

        Args:
            policy_id: The policy to remove.
        """
        self._request("DELETE", f"/policies/{policy_id}")

    # ------------------------------------------------------------------
    # Reconciliation
    # ------------------------------------------------------------------

    def list_reports(
        self,
        *,
        page: int = 1,
        per_page: int = 20,
    ) -> PaginatedResponse[ReconciliationReport]:
        """List reconciliation reports.

        Args:
            page: Page number (1-indexed).
            per_page: Results per page (max 100).

        Returns:
            Paginated list of reports.
        """
        params: Dict[str, Any] = {"page": page, "per_page": per_page}
        data = self._request("GET", "/reconciliation/reports", params=params)
        return PaginatedResponse(
            data=[self._parse_report(r) for r in data["data"]],
            total=data["total"],
            page=data["page"],
            per_page=data["per_page"],
            has_more=data["has_more"],
        )

    def trigger_reconciliation(self) -> ReconciliationReport:
        """Trigger an on-demand reconciliation run.

        Returns:
            The newly created report (initially in ``"running"`` status).
        """
        data = self._request("POST", "/reconciliation/trigger")
        return self._parse_report(data)

    # ------------------------------------------------------------------
    # Parsers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_payment(data: Dict[str, Any]) -> PaymentResponse:
        transactions = [
            Transaction(
                transaction_id=t["transaction_id"],
                from_agent_id=t["from_agent_id"],
                to_agent_id=t["to_agent_id"],
                amount=t["amount"],
                currency=t["currency"],
                status=TransactionStatus(t["status"]),
                created_at=t["created_at"],
                updated_at=t["updated_at"],
                memo=t.get("memo"),
                metadata=t.get("metadata"),
            )
            for t in data.get("transactions", [])
        ]
        escrow_raw = data.get("escrow_status")
        return PaymentResponse(
            payment_id=data["payment_id"],
            from_agent_id=data["from_agent_id"],
            to_agent_id=data["to_agent_id"],
            amount=data["amount"],
            currency=data["currency"],
            status=TransactionStatus(data["status"]),
            escrow_status=EscrowStatus(escrow_raw) if escrow_raw else None,
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            transactions=transactions,
            memo=data.get("memo"),
            metadata=data.get("metadata"),
        )

    @staticmethod
    def _parse_wallet(data: Dict[str, Any]) -> Wallet:
        return Wallet(
            wallet_id=data["wallet_id"],
            agent_id=data["agent_id"],
            currency=data["currency"],
            balance=data["balance"],
            available_balance=data["available_balance"],
            pending_balance=data["pending_balance"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )

    @staticmethod
    def _parse_policy(data: Dict[str, Any]) -> SpendingPolicy:
        return SpendingPolicy(
            policy_id=data["policy_id"],
            name=data["name"],
            agent_id=data.get("agent_id"),
            max_transaction_amount=data.get("max_transaction_amount"),
            daily_limit=data.get("daily_limit"),
            monthly_limit=data.get("monthly_limit"),
            allowed_currencies=data.get("allowed_currencies"),
            allowed_recipients=data.get("allowed_recipients"),
            require_escrow=data.get("require_escrow", False),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )

    @staticmethod
    def _parse_report(data: Dict[str, Any]) -> ReconciliationReport:
        return ReconciliationReport(
            report_id=data["report_id"],
            status=data["status"],
            started_at=data["started_at"],
            completed_at=data.get("completed_at"),
            total_transactions=data["total_transactions"],
            matched=data["matched"],
            unmatched=data["unmatched"],
            discrepancies=data.get("discrepancies", []),
        )

    # ------------------------------------------------------------------
    # Context manager / cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()

    def __enter__(self) -> "PulsePayments":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

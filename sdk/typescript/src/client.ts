/* ------------------------------------------------------------------ */
/*  Pulse Payments A2A SDK - Client                                   */
/* ------------------------------------------------------------------ */

import type {
  ListParams,
  PaginatedResponse,
  PaymentEvent,
  PaymentRequest,
  PaymentResponse,
  PolicyCreate,
  ReconciliationReport,
  SpendingPolicy,
  Wallet,
} from "./types.js";

import {
  AuthenticationError,
  ConflictError,
  NotFoundError,
  PulseApiError,
  RateLimitError,
} from "./errors.js";

/* ------------------------------------------------------------------ */
/*  Configuration                                                     */
/* ------------------------------------------------------------------ */

export interface PulsePaymentsConfig {
  /** API key issued from the Pulse dashboard. */
  apiKey: string;
  /** Override the default API base URL.  Defaults to `/pulse-api/`. */
  baseUrl?: string;
}

/* ------------------------------------------------------------------ */
/*  Client                                                            */
/* ------------------------------------------------------------------ */

export class PulsePayments {
  private readonly apiKey: string;
  private readonly baseUrl: string;

  constructor(config: PulsePaymentsConfig) {
    if (!config.apiKey) {
      throw new Error("apiKey is required");
    }
    this.apiKey = config.apiKey;
    // Ensure trailing slash so URL resolution works predictably.
    const base = config.baseUrl ?? "/pulse-api/";
    this.baseUrl = base.endsWith("/") ? base : `${base}/`;
  }

  /* ---------------------------------------------------------------- */
  /*  Internal HTTP helper                                            */
  /* ---------------------------------------------------------------- */

  private async request<T>(
    method: string,
    path: string,
    body?: unknown,
    query?: Record<string, string | number | undefined>,
  ): Promise<T> {
    // Build URL with optional query params.
    const url = new URL(path, this.baseUrl);
    if (query) {
      for (const [key, value] of Object.entries(query)) {
        if (value !== undefined) {
          url.searchParams.set(key, String(value));
        }
      }
    }

    const headers: Record<string, string> = {
      Authorization: `Bearer ${this.apiKey}`,
      Accept: "application/json",
    };

    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
    }

    const res = await fetch(url.toString(), {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });

    // ---- Error mapping ------------------------------------------------
    if (!res.ok) {
      let errorBody: { message?: string; code?: string } = {};
      try {
        errorBody = (await res.json()) as { message?: string; code?: string };
      } catch {
        // Response may not be JSON; fall through.
      }

      const msg = errorBody.message ?? res.statusText;

      switch (res.status) {
        case 401:
          throw new AuthenticationError(msg);
        case 404:
          throw new NotFoundError(msg);
        case 409:
          throw new ConflictError(msg);
        case 429: {
          const retryAfter = res.headers.get("Retry-After");
          throw new RateLimitError(
            msg,
            retryAfter ? parseInt(retryAfter, 10) : undefined,
          );
        }
        default:
          throw new PulseApiError(msg, res.status, errorBody.code);
      }
    }

    // 204 No Content
    if (res.status === 204) {
      return undefined as unknown as T;
    }

    return (await res.json()) as T;
  }

  /* ---------------------------------------------------------------- */
  /*  Payments                                                        */
  /* ---------------------------------------------------------------- */

  /**
   * Create a new payment between two agent wallets.
   */
  async requestPayment(payment: PaymentRequest): Promise<PaymentResponse> {
    return this.request<PaymentResponse>("POST", "payments", payment);
  }

  /**
   * Retrieve a single payment by its ID.
   */
  async getPayment(paymentId: string): Promise<PaymentResponse> {
    return this.request<PaymentResponse>("GET", `payments/${paymentId}`);
  }

  /**
   * List payments with optional filters and pagination.
   */
  async listPayments(
    params?: ListParams & { status?: string; wallet_id?: string },
  ): Promise<PaginatedResponse<PaymentResponse>> {
    return this.request<PaginatedResponse<PaymentResponse>>(
      "GET",
      "payments",
      undefined,
      params as Record<string, string | number | undefined>,
    );
  }

  /**
   * Retrieve lifecycle events for a specific payment.
   */
  async getPaymentEvents(paymentId: string): Promise<PaymentEvent[]> {
    return this.request<PaymentEvent[]>(
      "GET",
      `payments/${paymentId}/events`,
    );
  }

  /**
   * Open a dispute against a payment.
   */
  async disputePayment(
    paymentId: string,
    reason: { reason_code: string; description?: string },
  ): Promise<PaymentResponse> {
    return this.request<PaymentResponse>(
      "POST",
      `payments/${paymentId}/dispute`,
      reason,
    );
  }

  /* ---------------------------------------------------------------- */
  /*  Wallets                                                         */
  /* ---------------------------------------------------------------- */

  /**
   * Get a single wallet by ID.
   */
  async getWallet(walletId: string): Promise<Wallet> {
    return this.request<Wallet>("GET", `wallets/${walletId}`);
  }

  /**
   * List wallets with optional pagination.
   */
  async listWallets(
    params?: ListParams & { agent_id?: string },
  ): Promise<PaginatedResponse<Wallet>> {
    return this.request<PaginatedResponse<Wallet>>(
      "GET",
      "wallets",
      undefined,
      params as Record<string, string | number | undefined>,
    );
  }

  /**
   * Fund (credit) a wallet.
   */
  async fundWallet(
    walletId: string,
    payload: { amount: number; currency: string; memo?: string },
  ): Promise<Wallet> {
    return this.request<Wallet>(
      "POST",
      `wallets/${walletId}/fund`,
      payload,
    );
  }

  /**
   * Withdraw (debit) from a wallet.
   */
  async withdrawWallet(
    walletId: string,
    payload: { amount: number; currency: string; memo?: string },
  ): Promise<Wallet> {
    return this.request<Wallet>(
      "POST",
      `wallets/${walletId}/withdraw`,
      payload,
    );
  }

  /* ---------------------------------------------------------------- */
  /*  Spending Policies                                               */
  /* ---------------------------------------------------------------- */

  /**
   * Create a new spending policy.
   */
  async createPolicy(policy: PolicyCreate): Promise<SpendingPolicy> {
    return this.request<SpendingPolicy>("POST", "policies", policy);
  }

  /**
   * Retrieve a policy by ID.
   */
  async getPolicy(policyId: string): Promise<SpendingPolicy> {
    return this.request<SpendingPolicy>("GET", `policies/${policyId}`);
  }

  /**
   * List spending policies with optional pagination.
   */
  async listPolicies(
    params?: ListParams & { wallet_id?: string },
  ): Promise<PaginatedResponse<SpendingPolicy>> {
    return this.request<PaginatedResponse<SpendingPolicy>>(
      "GET",
      "policies",
      undefined,
      params as Record<string, string | number | undefined>,
    );
  }

  /**
   * Partially update an existing spending policy.
   */
  async updatePolicy(
    policyId: string,
    updates: Partial<PolicyCreate>,
  ): Promise<SpendingPolicy> {
    return this.request<SpendingPolicy>(
      "PATCH",
      `policies/${policyId}`,
      updates,
    );
  }

  /**
   * Delete a spending policy.
   */
  async deletePolicy(policyId: string): Promise<void> {
    return this.request<void>("DELETE", `policies/${policyId}`);
  }

  /* ---------------------------------------------------------------- */
  /*  Reports & Reconciliation                                        */
  /* ---------------------------------------------------------------- */

  /**
   * List reconciliation reports.
   */
  async listReports(
    params?: ListParams,
  ): Promise<PaginatedResponse<ReconciliationReport>> {
    return this.request<PaginatedResponse<ReconciliationReport>>(
      "GET",
      "reports/reconciliation",
      undefined,
      params as Record<string, string | number | undefined>,
    );
  }

  /**
   * Trigger a new reconciliation run and return the report stub.
   */
  async triggerReconciliation(payload?: {
    from?: string;
    to?: string;
  }): Promise<ReconciliationReport> {
    return this.request<ReconciliationReport>(
      "POST",
      "reports/reconciliation",
      payload,
    );
  }
}

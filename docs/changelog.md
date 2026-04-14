# Pulse Platform Changelog

All notable changes to the Pulse Platform are documented in this file.

---

## v1.7.0 (Spec) — Platform v4.18.0 — Exception Handling, Dispute Resolution & Advanced Settlement

*Designed — Queued for Build*

### Designed

- 5-phase dispute resolution lifecycle (filing → counterparty response → automated assessment → human arbitration → resolution enforcement)
- 6 dispute reason categories with structured evidence submission
- Automated dispute assessment using reconciliation matching engine
- Timeline enforcement at every phase with conservative timeout defaults
- Dispute-aware spending policy adjustment (>5% dispute rate triggers auto-tightening)
- Dispute rate added as 8th reconciliation detection category
- Chargeback pipeline with 6 reason codes, evidence windows, and automated evaluation
- Refund engine (full, partial, different-wallet) with approval workflows
- Credit/debit memo system for post-settlement adjustments
- Partial settlement: partial capture, split settlement, installment plans
- Batch settlement for micro-transaction aggregation
- Fee engine with 4 fee types (platform, processing, escrow, cross-org)
- Multi-currency FX with rate locking during escrow
- Dead letter queue with aging alerts and SLA tracking
- Idempotency enforcement via client-supplied keys
- Payment holds / admin freezes (emergency override)
- Statement generation (daily/weekly/monthly, PDF, per-agent/org/fund)
- Compliance audit exports with per-jurisdiction formatting and hash verification
- Transaction analytics API
- 20 new Pulse API routes (total: 50)
- 14 new webhook event types (total: 22)

### Platform Totals (projected)

| Metric | v1.6.5 | v1.7.0 | Delta |
|--------|---------|---------|-------|
| Pulse API Routes | 30 | 50 | +20 |
| Webhook Event Types | 8 | 22 | +14 |
| Reconciliation Categories | 7 | 8 | +1 |

---

## v1.6.5 (Spec) — Platform v4.17.0 (April 14, 2026) -- A2A Payment Infrastructure

### Added

- **Payment Agents:** Registered 3 new payment agents (#43 payment-authorization, #44 payment-settlement, #45 payment-reconciliation) with health check endpoints at `/pulse-api/agents/{name}/health`
- **Payment Tables:** Created 7 new data stores for transactions, wallets, authorizations, escrows, events, compliance logs, and reconciliation reports with row-level security enabled on all stores
- **Service Endpoints:** Deployed 5 new payment service endpoints exposing 13 endpoint checks
- **API Gateway Routes:** Added 15 payment routes to the Pulse API gateway under `/pulse-api/` prefix with SHA-256 authentication and per-route rate limiting
- **Permissions:** Introduced 9 new payment permissions (payments.process, payments.read, payments.refund, escrow.create, escrow.release, escrow.cancel, escrow.read, spending.evaluate, spending.read) enforced across 27 permission checks
- **Inter-Agent Routes:** Configured 13 new inter-agent communication routes connecting payment agents to each other and to existing platform agents (task-orchestrator, notification-agent, compliance-agent, reporting-agent)
- **Spending Policies:** Organization-level and agent-level spending policies with daily caps, per-transaction limits, and currency restrictions
- **Escrow Management:** Full escrow lifecycle support -- creation, hold, release, cancellation, and automatic expiry with refund
- **Webhook System:** Payment event webhook registration, delivery, and test endpoints with retry logic
- **Compliance Logging:** Automated compliance log entries for high-value transactions, multi-currency operations, and flagged activity
- **Reconciliation Engine:** Daily automated reconciliation with discrepancy detection, auto-resolution of rounding differences, and report generation
- **Scheduled Jobs:** Added daily reconciliation job (03:00 UTC) and hourly escrow expiry check
- **Smoke Tests:** Added 60 new tests (pay.1--pay.20 payment agent tests, AUTH-01--AUTH-14 authorization logic, SET-01--SET-14 settlement logic, REC-01--REC-12 reconciliation logic)

### Fixed

- **ESC-RACE-001 (Critical):** Concurrent dispute and expiry on same escrow within same second caused inconsistent state. Added row-level locking (SELECT FOR UPDATE) on escrow record before any state transition. Verified with 50 concurrent requests in load test.
- **ESC-RACE-002 (High):** Release and dispute arriving in same event loop tick produced unhandled error. Added guard clause that re-checks current state before transition and returns 409 Conflict if state has changed.
- **WALLET-PRECISION-001 (High):** Floating point arithmetic causing $0.01 discrepancies over 1,000+ transactions. All balance operations now use fixed-precision decimal with explicit rounding to 2 decimal places. Verified with 10,000 sequential transaction test.
- **WEBHOOK-RETRY-001 (Medium):** Webhook endpoint re-enabled but failure counter not reset, causing immediate re-disable on next failure. Re-enable operation now resets consecutive_failures to 0.

### Platform Totals

| Metric              | Count |
| ------------------- | ----- |
| Agents              | 45    |
| Service Endpoints   | 53    |
| Database Tables     | 79    |
| Inter-Agent Routes  | 49    |
| API Permissions     | 21    |
| Smoke Tests         | 284   |
| Connectors          | 93    |
| Vertical Templates  | 42    |

---

## v1.6.4 (Spec) — Platform v4.16.0 (April 13, 2026) -- Property Agent Architecture

### Added

- **Property Agents:** Registered agents #41 (property-listing) and #42 (property-matching) with hub-and-spoke architecture for vertical-specific workflows
- **Vertical Templates:** Expanded to 21 vertical templates with category-based toggle system for enabling/disabling per-organization features
- **Hub-and-Spoke Routing:** Implemented hub-and-spoke inter-agent routing model where the task-orchestrator acts as the central hub dispatching to vertical-specific spoke agents
- **PII Stripping:** Automated PII stripping on all outbound agent responses before delivery to external consumers, ensuring no personally identifiable information leaks through API responses
- **Multi-Language Dispatch:** Added multi-language prompt dispatch allowing agents to process and respond in the language of the originating request
- **Category Toggles:** Organization-level configuration toggles for enabling or disabling vertical categories (real estate, hospitality, retail, healthcare, etc.) without code changes

### Fixed

- **REC-TIMEZONE-001 (Medium):** Reconciliation window was calculated using server timezone instead of organization's configured timezone. Window is now derived from the organization's timezone setting, with start and end timestamps converted to UTC for the actual query.

### Platform Totals

| Metric              | Count |
| ------------------- | ----- |
| Agents              | 42    |
| Service Endpoints   | 48    |
| Database Tables     | 72    |
| Inter-Agent Routes  | 36    |
| Smoke Tests         | 224   |
| Connectors          | 93    |
| Vertical Templates  | 42    |

---

## v1.6.3 (Spec) — Platform v4.15.0 (April 13, 2026) -- Client API Gateway

### Added

- **SHA-256 Authentication:** All `/pulse-api/` routes secured with SHA-256 HMAC signature verification using client-issued API keys
- **API Routes:** Deployed 15+ client-facing API routes covering agent invocation, task management, connector configuration, organization settings, and reporting
- **HMAC Webhooks:** Outbound webhook payloads signed with HMAC-SHA256 to allow clients to verify authenticity of webhook deliveries
- **IP Whitelist:** Optional per-client IP whitelist enforcement at the gateway level, rejectable requests from non-whitelisted origins return 403
- **Rate Limiting:** Per-route rate limiting with configurable thresholds (requests per minute) and 429 responses with Retry-After headers
- **API Key Management:** Client API key generation, rotation, and revocation endpoints with audit trail logging

---

## v1.6.2 (Spec) — Platform v4.14.0 (April 13, 2026) -- Connector Registry

### Added

- **Connector Count:** Expanded the connector registry to 93 integrations spanning 21 industry verticals
- **Authentication Types:** Support for OAuth2 (authorization code and client credentials), API Key, and Basic Auth connector authentication
- **AES-256-GCM Encryption:** All stored connector credentials encrypted at rest using AES-256-GCM with per-tenant encryption keys
- **Connector Health Monitoring:** Automated health checks for all registered connectors with status dashboard and alerting on degraded connectors
- **Vertical Mapping:** Each connector tagged with one or more vertical categories enabling vertical-specific connector discovery and filtering
- **Credential Rotation:** Automated credential rotation support for OAuth2 connectors with token refresh and re-authorization flows

---

## v1.6.1 (Spec) — Platform v4.13.0 (April 13, 2026) -- Multi-Tenancy

### Added

- **Parent-Child Organizations:** Hierarchical organization model supporting parent organizations with unlimited child organizations, each with independent configuration
- **Database Isolation:** Row-level security policies enforcing strict data isolation between organizations at the database layer, preventing cross-tenant data access
- **Per-Org Agent Configuration:** Organization-specific agent configuration allowing each tenant to customize agent behavior, prompt templates, and enabled capabilities without affecting other tenants
- **Tenant Provisioning:** Automated tenant provisioning workflow that creates organization record, configures RLS policies, seeds default agent configurations, and issues initial API credentials
- **Org Switching:** API-level organization context switching allowing users with multi-org access to operate across organizations within a single session

### Fixed

- **RLS-RECURSION-001 (Critical):** RLS policies referencing a view with its own RLS caused infinite recursion under concurrent admin queries. Replaced circular view-based permission checks with direct permission-check functions that bypass the RLS layer for authorization decisions.

---

## v1.6.0 (Spec) — Platform v4.12.1 (April 13, 2026) -- Autonomous Scheduling

### Added

- **Cron Scheduling:** Cron-based job scheduling for recurring agent tasks with standard 5-field cron expression support and timezone-aware execution
- **Heartbeat Monitoring:** Agent heartbeat monitoring with configurable intervals and automatic alerting when agents fail to report within expected windows
- **Overlap Prevention:** Job-level overlap prevention ensuring that long-running scheduled tasks do not spawn duplicate executions if the previous run has not completed
- **Execution Timeouts:** Configurable per-job execution timeouts with automatic termination and failure logging when jobs exceed their allowed runtime
- **Job History:** Persistent job execution history with start time, end time, duration, exit status, and output capture for debugging and audit purposes

### Fixed

- **AUTH-WINDOW-001 (Medium):** Daily spend aggregation was off by one second at midnight UTC rollover. Switched to microsecond precision on time window boundaries with explicit inclusive-start, exclusive-end range.

---

## v1.5.0 (Spec) — Platform v4.12.0 (April 13, 2026) -- Inter-Agent Communication

### Added

- **Messaging Protocol:** Standardized inter-agent messaging protocol with typed message envelopes, correlation IDs, and delivery acknowledgment
- **Communication Routes:** Configured 36 inter-agent communication routes connecting all registered agents through the messaging backbone
- **Pipeline Categories:** Organized inter-agent flows into 4 pipeline categories: orchestration (task routing and delegation), data (information exchange and enrichment), notification (alert and status updates), and compliance (audit and regulatory flows)
- **Message Queue:** Persistent message queue with at-least-once delivery guarantees, dead-letter handling for undeliverable messages, and configurable retry policies
- **Route Discovery:** Dynamic route discovery allowing agents to query available communication routes and target agent capabilities at runtime
- **Message Tracing:** End-to-end message tracing with distributed trace IDs enabling full visibility into multi-agent conversation flows

### Fixed

- **AUTH-CONCURRENT-001 (Critical):** Two payment requests for same agent within 10ms both read daily spend as $900 (limit $1,000), both authorized $200, exceeding the limit. Introduced advisory lock keyed on agent_id + org_id during spend calculation to serialize concurrent checks.

---

*Maintained by TFSF Ventures FZ-LLC | RAKEZ License 47013955*

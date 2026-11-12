# Design Document — Usage Metering & Billing Engine

## 1. Project Overview

Usage Metering & Billing Engine is a multi-tenant backend service designed to track API and AI token consumption, enforce subscription quotas, calculate usage costs, and synchronize subscription status through Stripe.

The application supports two subscription plans: Free and Pro.

The primary objective is to build a reliable billing system that prevents duplicate usage records, enforces accurate quota limits, calculates costs using integer arithmetic, and processes subscription events securely.

## 2. Technology Stack

| Technology | Purpose |
|---|---|
| Python 3.13 | Backend programming language |
| FastAPI | REST API framework |
| PostgreSQL 15 | Relational database |
| Docker Compose | Database containerization |
| SQLAlchemy | Database ORM |
| Alembic | Database migrations |
| Pydantic | Request and response validation |
| Stripe Python SDK | Subscription and payment integration |
| Stripe CLI | Local webhook testing |
| Inngest | Background job processing |
| Pytest | Automated testing |
| GitHub | Version control and public repository |

## 3. System Architecture

The application follows a layered architecture to separate HTTP handling, business logic, database operations, and external integrations.

### 3.1 Application Layers

- API Layer: Handles HTTP requests, response formatting, and input validation.
- Service Layer: Implements usage metering, quota enforcement, cost calculation, and subscription management.
- Repository Layer: Handles database queries and persistence.
- Database Layer: Stores tenants, plans, subscriptions, usage events, and payment events.
- Integration Layer: Connects external services such as Stripe and Inngest.

### 3.2 Main Processing Flow

Client Request
    |
    v
FastAPI API Layer
    |
    v
Request Validation
    |
    v
Idempotency Check
    |
    v
Metering Service
    |
    v
Quota Enforcement
    |
    +---- Quota Exceeded
    |         |
    |         v
    |      HTTP 402 / 429
    |
    v
Cost Calculation
    |
    v
PostgreSQL Transaction
    |
    v
Usage Event Recorded
    |
    v
API Response

Stripe Checkout and verified webhooks handle subscription synchronization separately.

Inngest handles scheduled background processing.

## 4. Subscription Plans

The application initially supports two subscription plans.

| Plan | API Calls / Month | AI Tokens / Month | Monthly Price |
|---|---:|---:|---:|
| Free | 1,000 | 100,000 | $0 |
| Pro | 10,000 | 1,000,000 | $29 |

Pro pricing and quota values are configurable project assumptions.

The Pro subscription is available exclusively through Stripe Test Mode.

Usage periods follow UTC calendar months.

Quota usage is calculated independently for API calls and AI tokens.

Total AI token consumption is calculated as:

total_ai_tokens = input_tokens + output_tokens

Cached input tokens and reasoning tokens are subsets of their respective token categories and must not be counted twice.

## 5. Database Design

The application uses PostgreSQL and consists of seven main tables.

### 5.1 tenants

Stores customer organizations.

| Column | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| name | VARCHAR(150) | Tenant name |
| created_at | TIMESTAMPTZ | Creation timestamp |

### 5.2 plans

Stores subscription plan definitions and quota limits.

| Column | Type | Description |
|---|---|---|
| id | VARCHAR(20) | Primary key |
| api_call_limit | BIGINT | Monthly API call quota |
| ai_token_limit | BIGINT | Monthly AI token quota |
| monthly_price_cents | BIGINT | Monthly price in cents |
| currency | VARCHAR(3) | Currency code |
| is_active | BOOLEAN | Plan availability |

Initial plan records: free and pro.

### 5.3 subscriptions

Stores tenant subscription information.

| Column | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| tenant_id | UUID | Unique foreign key to tenants |
| plan_id | VARCHAR(20) | Foreign key to plans |
| stripe_customer_id | VARCHAR(255) | Stripe customer reference |
| stripe_subscription_id | VARCHAR(255) | Stripe subscription reference |
| status | VARCHAR(30) | Subscription status |
| current_period_start | TIMESTAMPTZ | Subscription period start |
| current_period_end | TIMESTAMPTZ | Subscription period end |
| created_at | TIMESTAMPTZ | Creation timestamp |
| updated_at | TIMESTAMPTZ | Last update timestamp |

Each tenant has one current subscription record.

Stripe customer and subscription identifiers must be unique when present.

### 5.4 idempotency_records

Stores request keys and original responses to prevent duplicate processing.

| Column | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| tenant_id | UUID | Foreign key to tenants |
| idempotency_key | VARCHAR(255) | Client request key |
| request_hash | VARCHAR(64) | SHA-256 request payload hash |
| response_status | INTEGER | Original HTTP status |
| response_body | JSONB | Original response |
| created_at | TIMESTAMPTZ | Creation timestamp |

Unique constraint:

(tenant_id, idempotency_key)

### 5.5 usage_events

Stores accepted billable usage records.

| Column | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| tenant_id | UUID | Foreign key to tenants |
| idempotency_record_id | UUID | Unique reference to idempotency record |
| api_calls | BIGINT | Number of API calls |
| input_tokens | BIGINT | Total input tokens |
| cached_input_tokens | BIGINT | Cached input subset |
| output_tokens | BIGINT | Total output tokens |
| reasoning_tokens | BIGINT | Reasoning subset of output |
| cost_micro_usd | BIGINT | Calculated cost |
| period_start | DATE | UTC billing month start |
| created_at | TIMESTAMPTZ | Usage timestamp |

Unique constraint:

idempotency_record_id

Each accepted billable request creates exactly one usage event.

### 5.6 stripe_events

Stores processed Stripe webhook event identifiers.

| Column | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| stripe_event_id | VARCHAR(255) | Unique Stripe event identifier |
| event_type | VARCHAR(100) | Stripe event type |
| processed_at | TIMESTAMPTZ | Processing timestamp |
| created_at | TIMESTAMPTZ | Event creation timestamp |

Unique constraint:

stripe_event_id

### 5.7 job_failures

Stores permanent background job failures.

| Column | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| function_id | VARCHAR(150) | Background function identifier |
| job_id | VARCHAR(255) | Job execution identifier |
| error_message | TEXT | Failure description |
| failed_at | TIMESTAMPTZ | Failure timestamp |

### 5.8 Database Constraints and Indexes

- All tenant-owned records must reference a valid tenant.
- Each tenant can have only one current subscription record.
- Each tenant can use an idempotency key only once.
- Each idempotency record can create only one usage event.
- Stripe webhook event identifiers must be unique.
- Usage queries must be indexed by tenant_id and period_start.
- Token quantities and monetary values must use integer types.
- Foreign keys must preserve referential integrity.
- Tenant ownership must be checked in every tenant-scoped database query.

Monthly usage is calculated by aggregating usage_events for the requested tenant and UTC billing period.

## 6. API Contract

The application exposes the following REST API endpoints.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | /health | API health check |
| POST | /v1/generate | Simulated billable operation |
| GET | /v1/usage | Retrieve monthly usage and cost |
| POST | /v1/billing/checkout-session | Create Stripe Checkout session |
| POST | /webhooks/stripe | Receive Stripe webhook events |

### 6.1 POST /v1/generate

Processes one simulated billable operation.

Required headers:

- X-Tenant-ID
- Idempotency-Key

Example request:

{
  "input_tokens": 1000,
  "cached_input_tokens": 200,
  "output_tokens": 500,
  "reasoning_tokens": 100
}

Validation rules:

- All token quantities must be non-negative integers.
- cached_input_tokens cannot exceed input_tokens.
- reasoning_tokens cannot exceed output_tokens.
- Missing required headers must be rejected.
- Unknown tenants must be rejected.

One successful request represents one API call.

The endpoint validates the request, checks quota availability, calculates costs, and records usage atomically.

### 6.2 GET /v1/usage

Returns the tenant's monthly usage summary.

The response includes:

- Current subscription plan.
- Subscription status.
- API calls used and remaining.
- AI tokens used and remaining.
- Monthly API call limit.
- Monthly AI token limit.
- Accumulated cost in micro-USD.
- Current UTC billing period.

### 6.3 POST /v1/billing/checkout-session

Creates a Stripe Checkout session for upgrading a Free tenant to Pro.

The endpoint:

1. Validates the tenant.
2. Creates or retrieves the Stripe customer.
3. Creates a subscription Checkout session.
4. Attaches tenant metadata.
5. Returns the Checkout URL.

The endpoint uses Stripe Test Mode exclusively.

### 6.4 POST /webhooks/stripe

Receives Stripe subscription events.

Supported events:

- checkout.session.completed
- customer.subscription.updated
- customer.subscription.deleted

The endpoint verifies the Stripe signature before processing any event.

Duplicate events must not cause repeated subscription updates.

## 7. Idempotency Strategy

Every billable request must include an Idempotency-Key header.

The request payload is normalized and hashed using SHA-256.

The system follows these rules:

- Same tenant, same key, same payload: return the original response without creating another usage event.
- Same tenant, same key, different payload: return HTTP 409 Conflict.
- Different tenants may use the same key independently.
- Concurrent requests using the same key must not create duplicate usage records.

### Transaction Strategy

The metering operation uses a PostgreSQL database transaction.

Processing sequence:

1. Validate request headers and payload.
2. Begin a database transaction.
3. Lock the tenant record using SELECT FOR UPDATE.
4. Check whether the idempotency key already exists.
5. Compare the stored request hash.
6. Calculate current monthly usage.
7. Enforce subscription quotas.
8. Calculate usage cost.
9. Insert the idempotency record and usage event.
10. Store the original response.
11. Commit the transaction.

Rejected quota requests may retain their original idempotency response but must never create a billable usage event.

Database unique constraints provide an additional safeguard against duplicate records.

## 8. Quota Enforcement

The system checks current monthly usage plus requested usage before accepting a billable operation.

The API call quota condition is:

current_api_calls + requested_api_calls <= api_call_limit

The AI token quota condition is:

current_ai_tokens + requested_ai_tokens <= ai_token_limit

Exactly reaching the quota limit is allowed.

A request exceeding the quota is rejected.

### HTTP Response Rules

- HTTP 402 Payment Required: Free-plan quota exhaustion requiring an upgrade, or a subscription that does not permit paid access.
- HTTP 429 Too Many Requests: Active Pro-plan quota exhaustion.

Responses must include a clear explanation of the rejection.

HTTP 429 responses include a Retry-After header indicating the time until the next UTC usage period.

Rejected requests must not create usage events.

Quota checks and usage recording must execute within the same database transaction to prevent concurrent requests from exceeding the available quota.

## 9. Cost Calculation

All monetary usage costs are stored as BIGINT in integer micro-USD.

Conversion:

1 USD = 1,000,000 micro-USD

Subscription prices are stored separately as integer cents.

### 9.1 Pinned Pricing Constants

| Usage Type | Price per Million Tokens |
|---|---:|
| Fresh input | $2.00 |
| Cached input | $1.00 |
| Output | $8.00 |
| API call | $0.001 per call |

These are illustrative project pricing assumptions, not official provider prices.

### 9.2 Token Calculation Rules

- Cached input tokens are a subset of input tokens.
- Reasoning tokens are a subset of output tokens.
- Fresh input tokens = input tokens - cached input tokens.
- Output pricing includes reasoning tokens.
- Reasoning tokens must never be counted twice.

### 9.3 Cost Formula

cost_micro_usd =
    (api_calls * 1000)
    + (fresh_input_tokens * 2)
    + (cached_input_tokens * 1)
    + (output_tokens * 8)

All calculations use integer arithmetic.

Monthly cost is calculated by summing the cost_micro_usd values of accepted usage events within the UTC billing period.

## 10. Stripe Integration

Stripe Test Mode handles Pro subscription checkout.

The application supports the following subscription lifecycle events:

- checkout.session.completed
- customer.subscription.updated
- customer.subscription.deleted

### 10.1 Webhook Security

- Verify the Stripe webhook signature using the webhook signing secret.
- Use the original raw request body during signature verification.
- Reject invalid signatures with HTTP 400.
- Never process unverified events.

### 10.2 Webhook Idempotency

Every Stripe event is identified by its unique event ID.

The system stores processed event IDs in stripe_events.

If an event is received more than once, the duplicate must be acknowledged without repeating its business operation.

Event deduplication and subscription updates must occur within a database transaction.

### 10.3 Subscription Synchronization

- checkout.session.completed: synchronize the completed Checkout subscription with its tenant.
- customer.subscription.updated: update the tenant's plan and subscription status.
- customer.subscription.deleted: downgrade the tenant to Free and update its subscription status.

Stripe remains the source of truth for payment and subscription events.

The local database mirrors verified Stripe information.

## 11. Background Processing

Inngest handles scheduled usage-summary processing.

The application implements a daily_usage_summary function.

### Configuration

- Trigger: Daily cron schedule at 00:05 UTC.
- Purpose: Aggregate tenant usage information for operational monitoring.
- Retry policy: Three retries.
- Failure handling: Persist permanent failures in job_failures.

The background function must not perform slow processing inside an HTTP request.

Failed executions must produce a traceable operational failure record.

## 12. Security and Reliability

The application implements the following controls:

- Store credentials in environment variables.
- Exclude .env from Git.
- Provide .env.example with placeholder values.
- Never expose Stripe secrets in logs or responses.
- Use Stripe Test Mode exclusively.
- Verify webhook signatures before processing.
- Enforce tenant-scoped database queries.
- Use database transactions for metering operations.
- Enforce idempotency through database constraints.
- Validate all incoming request data using Pydantic.
- Store monetary values using integer arithmetic.
- Use Alembic for database schema migrations.

X-Tenant-ID is used as a development tenant selector. It is not a substitute for production authentication or authorization.

## 13. Testing Strategy

The system will be validated through unit tests and integration tests.

Required test scenarios:

1. Successful billable request.
2. Duplicate request with the same idempotency key.
3. Same idempotency key with a different payload.
4. Concurrent requests using the same idempotency key.
5. Exact quota boundary acceptance.
6. Quota exceeded rejection.
7. Correct HTTP 402 and 429 responses.
8. Accurate AI token cost calculation.
9. Cached input token pricing.
10. Reasoning token calculation without double counting.
11. Monthly usage aggregation.
12. Stripe Checkout session creation.
13. Invalid webhook signature rejection.
14. Duplicate Stripe event handling.
15. Successful Free-to-Pro synchronization.
16. Pro-to-Free synchronization after subscription deletion.
17. Tenant data isolation.
18. Background job retry and permanent failure handling.

## 14. Non-Goals

The initial implementation intentionally excludes:

- Real AI model inference.
- Live payment processing.
- Invoice generation.
- Proration.
- Overage billing.
- Full frontend dashboard.
- Production-grade customer authentication.
- Complex multi-currency billing.

AI token usage will be simulated through API request parameters.

## 15. Project Deliverables

The final public GitHub repository must contain:

| File | Purpose |
|---|---|
| README.md | Project overview, architecture, setup, and limitations |
| DESIGN.md | System design and technical decisions |
| capstone.yaml | Machine-readable project manifest |
| EVIDENCE.md | Proof of all required acceptance criteria |
| BUILDLOG.md | Honest record of AI assistance and engineering decisions |
| .env.example | Environment variable template |
| docker-compose.yml | PostgreSQL container configuration |
| requirements.txt | Python dependencies |
| migrations/ | Database schema migrations |
| app/ | Backend application source code |
| tests/ | Automated test suite |

The repository must be public and dedicated to this capstone.

All implementation phases must be recorded through meaningful Git commits.

## 16. Phase 1 Completion Criteria

Phase 1 is complete when:

1. The database schema is defined.
2. Free and Pro plans and their quotas are documented.
3. The API contracts are established.
4. The idempotency strategy is documented.
5. Quota enforcement rules are defined.
6. Cost calculation rules are specified.
7. Stripe integration architecture is documented.
8. The design document is committed to the public repository.

The implementation must follow this document unless a technical limitation or justified design change requires an update.

# Capstone Evidence

Project: LLM Usage Metering & Billing Service
Author: Aldy Putra Manurung
Track: Backend AI Engineering
Cohort: July 2026
Date: 18 November 2026

## 1. Automated Testing

Last recorded full test:

- 145 passed
- 0 failed
- 0 skipped
- 2 warnings

Test modules include:

- test_atomic_usage_metering.py
- test_metering_concurrency.py
- test_usage_metering_service.py
- test_usage_api.py
- test_stripe_checkout_service.py
- test_stripe_webhook_service.py
- test_stripe_webhook_api.py
- test_stripe_event_repository.py
- test_stripe_subscription_sync.py
- test_background_job_persistence.py
- test_inngest_usage_reports.py

## 2. Behavioral Probes

| Probe | Evidence | Status |
|---|---|---|
| Idempotency | Metering and concurrency tests | Passed |
| Quota | Boundary and rejection tests | Passed |
| Stripe Checkout | Stripe Test Mode Checkout and webhook synchronization | Verified |
| Webhook Security | Signature and deduplication tests | Passed |
| Token Pricing | Cached input and reasoning token tests | Passed |

## 3. Stripe Checkout

A Stripe Test Mode checkout was completed for a test tenant.

Observed results:

- Initial plan: Free
- Product: FlyRank Pro
- Configured price: USD 29/month
- Final plan: Pro
- Subscription status: Active
- Event: checkout.session.completed

The PostgreSQL subscription record was synchronized through the webhook.

## 4. Webhook Hardening

Migration: 02775f8ad8e3

The subscription model stores last_stripe_event_created_at.

Out-of-order test:
- Newer subscription event processed.
- Older event received afterward.
- Older event identified as stale.
- Newer subscription state remained intact.

Automated tests also cover invalid signatures, missing signatures, and duplicate events.

A separate live Stripe CLI replay capture should be retained if required by the reviewer.

## 5. Inngest Verification

SDK: inngest 0.5.20

Local Inngest Dev Server successfully discovered the usage-report function.

### Successful job

Observed lifecycle:

queued -> running -> succeeded

The monthly report result was persisted in PostgreSQL.

### Permanent failure

A usage report job with an invalid billing period was submitted.

Observed lifecycle:

event received
-> worker execution
-> retries
-> inngest/function.failed
-> failure handler
-> job status failed
-> job_failures record persisted

Persisted error:

period_start must be the first day of a month.

This verifies local development failure handling. Cloud deployment has not been verified.

## 6. Database Migrations

Last recorded Alembic head:

6d0b2f9a4c71

Migration chain:

5a5f984af0ed
-> 02775f8ad8e3
-> 6d0b2f9a4c71

## 7. Remaining Submission Checks

- Retain Stripe CLI HTTP delivery logs.
- Capture live webhook replay evidence if required.
- Verify clean-environment installation.
- Confirm public GitHub repository access.
- Submit repository URL through FlyRank.

## 8. External Acceptance

FlyRank reviewer status: Not yet submitted / not yet accepted.

No certificate issuance is claimed.

# Build Log

Project: LLM Usage Metering & Billing Service
Author: Aldy Putra Manurung
Track: Backend AI Engineering
Cohort: July 2026

## 13 November 2026 - Database Foundation
- Created PostgreSQL schema.
- Added tenant, plan, subscription, idempotency, usage, Stripe event, and job failure tables.
- Added migration 5a5f984af0ed.

## 17 November 2026 - Metering and Stripe
- Implemented usage metering and API endpoints.
- Added Stripe customer and Checkout services.
- Added webhook foundations.
- Repository checkpoint: 0a4ece6.

## 18 November 2026 - Webhook Hardening
- Added webhook API router and subscription synchronization.
- Added event deduplication and subscription locking.
- Added stale-event protection.
- Added migration 02775f8ad8e3.
- Verified out-of-order event behavior.
- Recorded regression result: 134 passed.

## 18 November 2026 - Background Jobs
- Added BackgroundJob model.
- Added job lifecycle repository.
- Added permanent failure repository.
- Added monthly usage report service.
- Added migration 6d0b2f9a4c71.
- Added background job persistence tests.

## 18 November 2026 - Inngest
- Integrated Inngest Python SDK 0.5.20.
- Registered monthly usage report function.
- Added FastAPI Inngest serving route.
- Added event dispatch and worker execution.
- Configured three retries.
- Added permanent failure handling.
- Verified successful report generation using Inngest Dev Server.
- Verified permanent failure persistence after retry exhaustion.

## Regression Verification

Last recorded result:

145 passed
0 failed
0 skipped
2 warnings

Latest Alembic head:

6d0b2f9a4c71

## Engineering Decisions
- Preserved layered architecture.
- Used Stripe Test Mode.
- Used database transactions and constraints for idempotency.
- Used integer micro-USD for cost calculations.
- Kept report generation outside the HTTP request path.
- Reused the existing job_failures table.
- Added background_jobs for job status and report results.
- Used Inngest Dev Server for local development.

## AI Assistance Disclosure

ChatGPT assisted with architecture discussion, code drafting, debugging, test analysis, and documentation.

The developer executed commands, reviewed changes, ran tests, and verified integration behavior.

AI-generated code was not treated as proof of correctness. Reported results are based on observed test and terminal output.

## Known Limitations
- Production deployment has not been verified.
- Inngest cloud credentials are not configured locally.
- Stripe Live Mode is outside project scope.
- Production authentication is not implemented.
- External FlyRank review has not occurred.

## Submission Status

Documentation prepared locally.

Changes still require Git review, commit, push, and external submission.

No acceptance or certificate is claimed.

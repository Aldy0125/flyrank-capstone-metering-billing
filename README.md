# LLM Usage Metering & Billing Service

Multi-tenant usage metering and billing backend using FastAPI, PostgreSQL, Stripe, and Inngest.

Author: Aldy Putra Manurung
Track: Backend AI Engineering
Cohort: July 2026

Repository: https://github.com/Aldy0125/flyrank-capstone-metering-billing

## Features
- Multi-tenant usage metering
- Request idempotency
- Transactional usage recording
- API and AI token quota enforcement
- Integer micro-USD cost calculation
- Stripe Checkout Test Mode
- Webhook signature verification
- Stripe event deduplication
- Subscription synchronization
- Out-of-order event protection
- Asynchronous usage reports
- Inngest retries and failure persistence

## Technology
- Python 3.13
- FastAPI
- PostgreSQL 15
- SQLAlchemy
- Alembic
- Stripe Python SDK
- Inngest 0.5.20
- Docker Compose
- Pytest

## Installation
1. Create virtual environment: py -3.13 -m venv .venv
2. Activate: .\.venv\Scripts\Activate.ps1
3. Install: pip install -r requirements.txt
4. Configure .env using .env.example.
5. Start database: docker compose up -d db
6. Apply migrations: python -m alembic upgrade head
7. Run API: python -m uvicorn app.main:app --reload --port 8000

Swagger: http://127.0.0.1:8000/docs

## Inngest Development
Terminal 1:
$env:INNGEST_DEV = "1"
python -m uvicorn app.main:app --reload --port 8000

Terminal 2:
docker run --rm -p 8288:8288 -p 8289:8289 inngest/inngest inngest dev -u http://host.docker.internal:8000/api/inngest

Dashboard: http://localhost:8288

## API Endpoints
- GET /health
- POST /v1/generate
- GET /v1/usage
- POST /v1/billing/checkout-session
- POST /webhooks/stripe
- POST /v1/usage/reports
- GET /v1/usage/reports/{job_id}

## Background Jobs
Monthly usage reports run asynchronously through Inngest.
Job states: queued, running, succeeded, failed.
Three retries are configured. Permanent failures are persisted in job_failures.

## Testing
Run: python -m pytest -q

Last recorded result (18 November 2026):
145 passed, 0 failed, 0 skipped, 2 warnings.

## Limitations
- Stripe Live Mode is not enabled.
- Real AI inference is outside project scope.
- X-Tenant-ID is a development tenant selector, not production authentication.
- Production deployment has not been verified.
- Invoice generation, proration, and overage billing are outside current scope.

## Documentation
- DESIGN.md
- EVIDENCE.md
- BUILDLOG.md
- capstone.yaml

No open-source license has been declared.

## Demo Data Initialization

After PostgreSQL is running, initialize the default Free and Pro plans:

1. Start PostgreSQL: docker compose up -d db
2. Apply migrations: python -m alembic upgrade head
3. Seed plans: python -m app.seed

The seed operation is safe to repeat. Existing plan configurations are validated and never automatically overwritten.

## Run Application

Run: python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

API documentation: http://127.0.0.1:8000/docs

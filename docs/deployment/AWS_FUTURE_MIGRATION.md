# AWS: future migration (design only — nothing is provisioned)

The private beta runs on one Linux machine. Move to AWS only when a trigger below is observed, not because this plan
exists. Figures from the 03 cost plan are **illustrative planning ranges, not quotes**: recalculate with the AWS
Pricing Calculator for the chosen region and real traffic before committing.

## What already makes the move easy

| Beta today | AWS target | Seam in the code |
|---|---|---|
| Local files on the `storage` volume | S3 private bucket, pre-signed downloads (minutes) | `backend/services/storage.py` (`LocalStorage` / `S3Storage`, keys not paths) |
| Postgres container | RDS PostgreSQL (Multi-AZ when justified) | `DATABASE_URL`; Alembic migrations |
| In-process APScheduler | EventBridge Scheduler → ECS task / Lambda per job | `backend/services/jobs_registry.py` (`run(name)` is one call per job) |
| SMTP (optional) | SES | `backend/services/email_service.py` |
| Docker logs + JSON formatter | CloudWatch Logs + metrics/alarms | `core/logging_setup.py` |
| `.env` | Secrets Manager / Parameter Store | `backend/config.py` reads env vars |
| nginx container | CloudFront + ALB (or CloudFront → ECS/EC2) | same-origin `/api` routing |
| Optional later | ElastiCache Redis, OpenSearch | only on the triggers below |

## Planning ranges from the 03 plan (USD/month, before AI/data/legal/mentor costs)

* Lean beta, 100–500 candidates: **$57–163**
* Small production: **$155–370**
* Growth: **$320–1,030**

Track: total platform cost per monthly active candidate, cost per interview and per offer, AI spend per workflow
(`ai_calls.cost_usd` by `purpose`, shown on Admin → Product metrics) and resume export rendering load.

## Cost controls when on AWS
Budgets with alerts at **50% / 80% / 100%**, cost-allocation tags (`app=jobpilot`, `env`, `component`), S3 lifecycle
rules for old exports, RDS right-sizing and storage autoscaling caps, no NAT Gateway unless required (use VPC
endpoints), log retention limits.

## Upgrade triggers (any one)
* The single machine's uptime or recovery time is hurting users (repeated outages, RTO > 1 h needed lower).
* Background jobs contend with requests (slow pages during discovery) or the job queue backs up.
* Sustained database I/O or storage growth beyond the host.
* Resume export queues (rendering latency) or ingestion spikes.
* Search needs that Postgres full-text can't meet; global traffic needing a CDN.

## Avoid until triggered
EKS/Kubernetes, OpenSearch, Kafka, microservices, NAT Gateways, multi-region, paid APM.

## Infrastructure as code (when the time comes)
Terraform with separate `beta`/`prod` workspaces and state, CI/CD via approved pipeline (plan on PR, apply on
merge with manual approval), backups (RDS automated + snapshot copy, S3 versioning), and the tagging above.

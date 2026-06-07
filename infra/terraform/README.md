# pdlcflow — multi-cloud Terraform (AWS · GCP · Azure)

Deploy the pdlcflow SaaS stack to **any of the three major clouds** with parallel,
full-parity Terraform modules. Each module mirrors the AWS CDK's 8 stacks using that
cloud's managed services, so you `terraform apply` and get the whole runtime.

> The original [`infra/cdk/`](../cdk/) (TypeScript AWS CDK) remains the AWS-native option;
> this Terraform layout is the portable, multi-cloud path.

```
infra/terraform/
├── modules/
│   ├── aws/     # VPC · RDS · ElastiCache · S3 · ECS Fargate+ALB · CloudFront · Cognito · Firehose+Glue · Bedrock IAM · Secrets Manager · CloudWatch
│   ├── gcp/     # VPC · Cloud SQL · Memorystore · GCS · Cloud Run · Cloud CDN · Identity Platform · Pub/Sub+BigQuery · Vertex AI · Secret Manager
│   └── azure/   # VNet · Postgres Flexible · Azure Cache · Storage+CDN · Container Apps · AD B2C · Event Hubs · Azure OpenAI · Key Vault · Log Analytics
└── example.tfvars
```

## Service mapping (parity)

| Concern | AWS | GCP | Azure |
| --- | --- | --- | --- |
| Network | VPC + NAT | VPC + Serverless Connector | VNet |
| Postgres | RDS | Cloud SQL | Postgres Flexible Server |
| Redis | ElastiCache | Memorystore | Azure Cache for Redis |
| Object storage | S3 | Cloud Storage | Blob Storage |
| API + worker | ECS Fargate + ALB | Cloud Run | Container Apps |
| Studio CDN | CloudFront | Cloud CDN | Azure CDN |
| Identity | Cognito | Identity Platform | AD B2C |
| Clickstream stream | Firehose + Glue | Pub/Sub + BigQuery | Event Hubs |
| LLM | Bedrock | Vertex AI | Azure OpenAI |
| Secrets | Secrets Manager | Secret Manager | Key Vault |
| Logs | CloudWatch | Cloud Logging | Log Analytics |

## Deploy

```bash
cd infra/terraform/modules/<aws|gcp|azure>
terraform init
terraform apply -var-file=../../example.tfvars   # after copying + editing it
```

Provide credentials the usual way per provider (`AWS_*` / `gcloud auth application-default` /
`az login` + `ARM_SUBSCRIPTION_ID`). Key inputs (see each module's `variables.tf`): `api_image`
(pin a release), `db_password` (sensitive), region/location, and `app_env` (extra `PDLC_*`).
After apply, build + upload the Studio SPA to the `studio` bucket/storage (see outputs) and run
migrations: `… run --rm api uv run alembic upgrade head` against the new database.

## Status & honest caveats

**Validated, not deploy-tested.** Every module passes `terraform validate` / `tofu validate`
(schema-correct against the real provider schemas), but has **not** been applied to a live
cloud account. Before production: pin provider versions, run `terraform plan` in your account,
and review IAM/networking for your security posture.

**App portability** — what works as-is vs. needs an adapter:

- ✅ **Postgres, Redis, the 7-provider LLM factory** (Bedrock / Vertex / Azure OpenAI) and
  **local-JWT auth** are fully portable and used by the app on every cloud.
- ⚠️ **Object storage:** the app's artifact store speaks the **S3 API**. AWS S3 is native; GCS
  works via its S3-compatible endpoint (set `PDLC_S3_ENDPOINT_URL` + HMAC keys); **Azure Blob is
  not S3-compatible** — use the DB/filesystem artifact store there until a Blob adapter lands.
  (The buckets are provisioned on all three.)
- ⚠️ **Managed identity:** the app's `cognito` auth mode is AWS-specific. On GCP/Azure use
  `PDLC_AUTH_MODE=local` (JWT) or wire OIDC against Identity Platform / AD B2C (a follow-on).
- ⚠️ **Clickstream streaming:** only AWS has a native Firehose sink in the app today, so the
  GCP/Azure modules default the app to the **Postgres clickstream sink**; the provisioned
  Pub/Sub+BigQuery / Event Hubs are ready for a native sink adapter (a follow-on).

These are app-adapter follow-ons, not infrastructure gaps — the Terraform provisions the
full parity stack on each cloud.

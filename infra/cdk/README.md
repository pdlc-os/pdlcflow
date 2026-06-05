# SaaS (AWS CDK)

Eight stacks; deploy in dependency order with `cdk deploy --all`.

## Stacks

| Stack | Purpose |
|---|---|
| `pdlcflow-network`       | VPC, 2 AZs, public + private subnets, NAT |
| `pdlcflow-data`          | Aurora Serverless v2 (Postgres 17), ElastiCache Redis RG, S3 buckets |
| `pdlcflow-compute`       | ECS Fargate cluster, ALB-backed API service, Arq worker service |
| `pdlcflow-edge`          | CloudFront + S3 for Studio bundle |
| `pdlcflow-auth`          | Cognito user pool + Hosted UI |
| `pdlcflow-events`        | Kinesis Firehose → S3 → Glue catalog (ClickHouse Cloud peering external) |
| `pdlcflow-bedrock`       | IAM role for engine + worker tasks to invoke Bedrock |
| `pdlcflow-observability` | CloudWatch log groups + dashboard |

## Quickstart

```bash
pnpm install
pnpm cdk bootstrap aws://<account>/us-east-1
pnpm cdk deploy --all
```

## Phase A status

This skeleton compiles and synths today. Production-readiness items deferred to Phase H:

- KMS CMK per tenant (currently using AWS-managed keys)
- Cognito federated identity providers for SSO
- VPC endpoints for S3/Secrets Manager/Bedrock
- Auto-scaling policies on the ECS services
- Multi-region failover
- BYOA tenant onboarding wizard + per-tenant role
- ClickHouse Cloud peering CFN

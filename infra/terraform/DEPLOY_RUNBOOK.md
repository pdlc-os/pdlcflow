# First cloud deploy — runbook & checklist (T4-4)

The Terraform modules are **schema-valid but never applied** (see
[README](README.md) → *Status & honest caveats*). The first real deploy is a
**milestone**, not a `terraform apply` you assume works. This runbook is the
checklist to walk it deliberately — state backend, secrets, image refs, DNS,
auth — plus the verification and rollback steps.

Treat the first apply per cloud as a staging/dev environment. Only after the
verification section passes end-to-end should the same procedure be promoted to
production.

---

## 0. Prerequisites

- [ ] Cloud account + credentials (`AWS_*` / `gcloud auth application-default` /
      `az login` + `ARM_SUBSCRIPTION_ID`), scoped to the target project/subscription.
- [ ] Terraform ≥ 1.6 (or OpenTofu ≥ 1.6). Provider versions **pinned** in each
      module's `versions.tf` (do not float on first deploy).
- [ ] A built, pushed **API image** at a real tag (see §3). Do **not** deploy `latest`.
- [ ] Decide the **auth model** now (§6): local JWT (single-tenant) or OIDC (SSO).

## 1. Remote state backend (do this first)

The modules ship without a backend block so `validate` stays offline. **Never**
run the first apply with local state — configure a remote, locked backend before
`init`:

- **AWS** — S3 bucket (versioned) + DynamoDB lock table.
- **GCP** — GCS bucket (object versioning on).
- **Azure** — Storage Account + Blob container.

```hcl
# backend.tf (create in the chosen module dir; values are yours, not defaults)
terraform {
  backend "s3" {            # or "gcs" / "azurerm"
    bucket = "pdlcflow-tfstate-<env>"
    key    = "pdlcflow/<env>/terraform.tfstate"
    region = "<region>"
    dynamodb_table = "pdlcflow-tflock"
    encrypt = true
  }
}
```

- [ ] Backend bucket/table created out-of-band (chicken-and-egg: don't manage the
      state bucket in the same state).
- [ ] `terraform init` succeeds against the remote backend.

## 2. Secrets

Nothing sensitive belongs in `*.tfvars` committed to git. Provision secrets in
the cloud secret manager (Secrets Manager / Secret Manager / Key Vault — the
modules create the vault) and pass only references:

- [ ] `db_password` — generate a strong value; pass via `-var` from your secret
      store or `TF_VAR_db_password`, never a file in git.
- [ ] `jwt_secret` (`PDLC_JWT_SECRET`) — 32+ random bytes if using local auth.
- [ ] LLM provider credentials — prefer the cloud's managed identity (Bedrock IAM
      role / Vertex service account / Azure OpenAI managed identity) over static keys.
- [ ] Repo tokens for the execution arc (`token_secret_ref`), if self-host
      execution will run there — but note execution is single-user self-host only
      and should **not** be enabled on a multi-tenant SaaS deploy.

## 3. Image references (pin a release)

- [ ] `api_image` = `ghcr.io/pdlc-os/pdlcflow-api:vX.Y.Z` (a released tag from
      `release-images.yml`), not `:latest`.
- [ ] Confirm the tag exists + is multi-arch (the release workflow builds
      `linux/amd64,linux/arm64`).
- [ ] Studio + nexus-dashboard images likewise pinned where the module consumes them.

## 4. Apply

```bash
cd infra/terraform/modules/<aws|gcp|azure>
cp ../../example.tfvars ./<env>.tfvars   # then EDIT: region, api_image, sizes, app_env
terraform init
terraform plan  -var-file=./<env>.tfvars   # REVIEW every create — especially IAM + networking
terraform apply -var-file=./<env>.tfvars
```

- [ ] `plan` reviewed for IAM scope, security-group/firewall ingress, public
      exposure. Nothing world-open that shouldn't be.
- [ ] `apply` clean; capture the **outputs** (URLs, bucket names, DB host).

## 5. Post-apply app bring-up

- [ ] **Migrations:** `… run --rm api uv run alembic upgrade head` against the new
      database (ECS run-task / Cloud Run job / Container Apps job).
- [ ] **Studio SPA:** build (`cd apps/studio && pnpm build`) and upload `dist/` to
      the `studio` bucket/storage from the outputs; invalidate the CDN.
- [ ] **Artifact store:** set `PDLC_ARTIFACT_STORE` appropriately — S3 on AWS;
      GCS via its S3-compatible endpoint (`PDLC_S3_ENDPOINT_URL` + HMAC keys) on
      GCP; **filesystem/DB on Azure** (Blob is not S3-compatible yet).
- [ ] **Clickstream sink:** AWS → Firehose; GCP/Azure → default Postgres sink
      (the provisioned Pub/Sub+BigQuery / Event Hubs await a native sink adapter).

## 6. Auth / identity

- [ ] **Local (single-tenant):** `PDLC_AUTH_MODE=local`, set `PDLC_JWT_SECRET`,
      `PDLC_BOOTSTRAP_ADMIN_EMAIL/PASSWORD` for the first admin.
- [ ] **OIDC (SSO):** `PDLC_AUTH_MODE=oidc` + `PDLC_AUTH_REQUIRED=true`, with
      `PDLC_OIDC_ISSUER`, `PDLC_OIDC_AUDIENCE`, `PDLC_OIDC_CLIENT_ID`,
      `PDLC_OIDC_REDIRECT_URI` (the Studio origin), and the claim mappings
      (`PDLC_OIDC_ORG_CLAIM`, `PDLC_OIDC_ROLE_CLAIM`). Works against Cognito,
      Google Identity Platform, Entra/AD B2C, or Auth0. The engine **refuses to
      boot** if issuer/audience are missing — that's expected.
- [ ] Register the Studio redirect URI as an allowed callback in the IdP; enable
      the auth-code + PKCE flow for a public client.

## 7. DNS + TLS

- [ ] Point the API hostname at the load balancer / Cloud Run / Container App
      ingress from the outputs.
- [ ] Point the Studio hostname at the CDN distribution.
- [ ] TLS certs issued + attached (ACM / managed certs / App Service cert).
- [ ] CORS: the API allows the Studio origin.

## 8. Verification (must all pass before promoting)

- [ ] `GET /health` → 200; `GET /health/ready` → `{"status":"ready"}` with
      `db`/`redis` healthy (a degraded DB returns 503 — do not proceed).
- [ ] Sign in end-to-end (local admin, or the full OIDC redirect → callback →
      session). `GET /v1/auth/me` returns the identity with the right org/role.
- [ ] Start a `/brainstorm` (or `/init`) run; confirm an approval gate surfaces
      over the WebSocket and resolves.
- [ ] An artifact write + read round-trips (the project Memory panel lists it).
- [ ] One LLM completion succeeds against the cloud's provider; a
      `llm.tokens_spent` event lands in the clickstream.
- [ ] Nexus dashboard renders (rollups non-empty after the above).

## 9. Rollback

- [ ] Roll the API service back to the previous pinned image tag (blue/green or
      revision rollback per platform) — the fastest recovery.
- [ ] `terraform apply` of the prior state/vars for infra-level changes; keep the
      previous plan output.
- [ ] DB migrations are forward-only — restore from an automated snapshot if a
      migration must be undone. Take a manual snapshot **before** step 5.

---

**When this runbook has been walked successfully on a cloud, update
[README](README.md) → *Status* to record that module as deploy-tested (with the
date + environment), and delete its "validated, not deploy-tested" caveat for
that provider.** Until then the honest status stands.

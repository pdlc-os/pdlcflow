# Copy to <cloud>.tfvars and fill in. Pass with: terraform apply -var-file=../../<cloud>.tfvars
# (run from infra/terraform/modules/<cloud>/). Pin api_image to a release.

# --- common ---
api_image   = "ghcr.io/pdlc-os/pdlcflow-api:1.5.0"
db_password = "CHANGE-ME-strong-password"

# --- aws ---    region = "us-east-1"
# --- gcp ---    project_id = "my-gcp-project"   region = "us-central1"
# --- azure ---  location = "eastus"             storage_account_name = "pdlcflowstoreXXXX"  # globally unique

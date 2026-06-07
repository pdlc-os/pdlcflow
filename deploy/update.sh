#!/usr/bin/env bash
# pdlcflow updater.
#
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/pdlc-os/pdlcflow/main/deploy/update.sh)"
#
# Refreshes the deploy files (compose + scripts; NOT your .env), pulls the latest
# images, recreates the stack, and applies any new DB migrations. Run from your
# deploy dir (or above ./pdlcflow), or pass --dir=<path>.
#
# Options:
#   --version=<v>   pin PDLCFLOW_VERSION in .env (e.g. --version=1.6.0), then update
#   --dir=<path>    deploy location (default: ./ or ./pdlcflow)
#   --no-migrate    skip `alembic upgrade head`
set -euo pipefail

BASE="${PDLCFLOW_BASE:-https://raw.githubusercontent.com/pdlc-os/pdlcflow/main/deploy}"
DIR="${PDLCFLOW_DIR:-}"; VERSION=""; MIGRATE=1
for a in "$@"; do
  case "$a" in
    --dir=*) DIR="${a#--dir=}" ;;
    --version=*) VERSION="${a#--version=}" ;;
    --no-migrate) MIGRATE=0 ;;
    *) echo "unknown option: $a" >&2; exit 2 ;;
  esac
done

c() { printf '\033[1;36m%s\033[0m\n' "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "✗ '$1' is required but not found." >&2; exit 1; }; }
need curl; need docker

if [ -z "$DIR" ]; then
  if [ -f docker-compose.yml ]; then DIR="."
  elif [ -f pdlcflow/docker-compose.yml ]; then DIR="pdlcflow"
  else echo "✗ No pdlcflow deployment found here. Run from the deploy dir or pass --dir=<path>." >&2; exit 1; fi
fi
[ -f "$DIR/docker-compose.yml" ] || { echo "✗ $DIR/docker-compose.yml not found." >&2; exit 1; }
cd "$DIR"
c "Updating pdlcflow in $(pwd)"

c "↓ Refreshing deploy files (your .env is left untouched)"
curl -fsSLO "$BASE/docker-compose.yml"
for f in setup.sh install.sh update.sh uninstall.sh; do
  curl -fsSL "$BASE/$f" -o "$f" && chmod +x "$f"
done
mkdir -p postgres-init && curl -fsSL "$BASE/postgres-init/01-app-role.sh" -o postgres-init/01-app-role.sh

if [ -n "$VERSION" ]; then
  if [ -f .env ] && grep -q '^PDLCFLOW_VERSION=' .env; then
    sed -i.bak "s/^PDLCFLOW_VERSION=.*/PDLCFLOW_VERSION=${VERSION}/" .env && rm -f .env.bak
  else
    echo "PDLCFLOW_VERSION=${VERSION}" >> .env
  fi
  c "→ Pinned PDLCFLOW_VERSION=${VERSION}"
fi

c "⬇  Pulling images"
docker compose pull
c "🚀 Recreating containers"
docker compose up -d
if [ "$MIGRATE" -eq 1 ]; then
  c "🗄  Applying database migrations"
  docker compose run --rm api uv run alembic upgrade head
fi

echo
c "✓ Update complete."
echo "   Studio:  http://localhost:8080   ·   API: http://localhost:8000/health"

#!/usr/bin/env bash
# pdlcflow uninstaller.
#
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/pdlc-os/pdlcflow/main/deploy/uninstall.sh)"
#
# Stops + removes the stack. By default it KEEPS your data and deploy files, then
# asks (default No) before each irreversible step. Run from your deploy dir (or
# above ./pdlcflow), or pass --dir=<path>.
#
# Options:
#   --dir=<path>   deploy location (default: ./ or ./pdlcflow)
#   --data         also delete data volumes (Postgres/MinIO/artifacts) — IRREVERSIBLE
#   --images       also remove pulled ghcr.io/pdlc-os/pdlcflow-* images
#   --purge        --data + --images + remove the deploy directory
#   --yes, -y      don't prompt; only the actions you flagged happen (default: down only)
set -euo pipefail

DIR="${PDLCFLOW_DIR:-}"; YES=0; DO_DATA=0; DO_IMG=0; DO_DIR=0
for a in "$@"; do
  case "$a" in
    --dir=*) DIR="${a#--dir=}" ;;
    --data) DO_DATA=1 ;;
    --images) DO_IMG=1 ;;
    --purge) DO_DATA=1; DO_IMG=1; DO_DIR=1 ;;
    --yes|-y) YES=1 ;;
    *) echo "unknown option: $a" >&2; exit 2 ;;
  esac
done

c() { printf '\033[1;36m%s\033[0m\n' "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "✗ '$1' is required but not found." >&2; exit 1; }; }
confirm() { local a; read -r -p "$1 (y/N): " a; [[ "$a" =~ ^[Yy] ]]; }
need docker

if [ -z "$DIR" ]; then
  if [ -f docker-compose.yml ]; then DIR="."
  elif [ -f pdlcflow/docker-compose.yml ]; then DIR="pdlcflow"
  else echo "✗ No pdlcflow deployment found here. Run from the deploy dir or pass --dir=<path>." >&2; exit 1; fi
fi
[ -f "$DIR/docker-compose.yml" ] || { echo "✗ $DIR/docker-compose.yml not found." >&2; exit 1; }
abs="$(cd "$DIR" && pwd)"
c "Uninstalling pdlcflow at $abs"

# Resolve the irreversible actions (flags, then prompts unless --yes).
if [ "$YES" -eq 0 ]; then
  if [ "$DO_DATA" -eq 0 ] && confirm "Delete ALL DATA (Postgres / MinIO / artifacts volumes)? Irreversible"; then DO_DATA=1; fi
  if [ "$DO_IMG" -eq 0 ] && confirm "Remove pulled pdlcflow images?"; then DO_IMG=1; fi
  if [ "$DO_DIR" -eq 0 ] && confirm "Remove the deploy directory ($abs)?"; then DO_DIR=1; fi
fi

cd "$abs"
if [ "$DO_DATA" -eq 1 ]; then
  c "⏹  Removing containers, network, AND data volumes"
  docker compose down -v --remove-orphans
else
  c "⏹  Removing containers + network (keeping data volumes)"
  docker compose down --remove-orphans
fi

if [ "$DO_IMG" -eq 1 ]; then
  imgs="$(docker images --format '{{.Repository}}:{{.Tag}}' | grep '^ghcr.io/pdlc-os/pdlcflow-' || true)"
  if [ -n "$imgs" ]; then docker rmi $imgs >/dev/null 2>&1 || true; c "→ Removed pdlcflow images"; fi
fi

if [ "$DO_DIR" -eq 1 ]; then
  cd ..
  rm -rf "$abs"
  c "→ Removed $abs"
fi

echo
c "✓ pdlcflow uninstalled."
[ "$DO_DATA" -eq 0 ] && echo "   Data volumes were kept — re-run with --data (or 'docker compose down -v') to delete them."

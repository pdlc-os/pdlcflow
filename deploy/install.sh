#!/usr/bin/env bash
# pdlcflow one-line installer.
#
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/pdlc-os/pdlcflow/main/deploy/install.sh)"
#
# Downloads the deploy files into ./pdlcflow, runs the interactive setup wizard
# (prompts + generates secrets → .env), then brings the stack up and applies the
# schema. Use the `bash -c "$(curl …)"` form (not `curl | bash`) so the wizard's
# prompts can read from your terminal.
#
# Options (env or flags):
#   PDLCFLOW_DIR=<dir> | --dir=<dir>   install location (default: ./pdlcflow)
#   --no-start                         download + configure only (don't `up`/migrate)
set -euo pipefail

BASE="${PDLCFLOW_BASE:-https://raw.githubusercontent.com/pdlc-os/pdlcflow/main/deploy}"
DIR="${PDLCFLOW_DIR:-pdlcflow}"
START=1
for a in "$@"; do
  case "$a" in
    --no-start) START=0 ;;
    --dir=*) DIR="${a#--dir=}" ;;
    *) echo "unknown option: $a" >&2; exit 2 ;;
  esac
done

c() { printf '\033[1;36m%s\033[0m\n' "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "✗ '$1' is required but not found on PATH." >&2; exit 1; }; }

# --- pdlcflow CLI: PATH symlink + PDLCFLOW_HOME env (shared by install/update/uninstall) ---
PDLCFLOW_BIN_DIR="${PDLCFLOW_BIN_DIR:-$HOME/.local/bin}"
_rc_file() { case "${SHELL:-}" in *zsh) echo "$HOME/.zshrc";; *bash) echo "$HOME/.bashrc";; *) echo "$HOME/.profile";; esac; }
_rc_strip() { local f="$1"; [ -f "$f" ] || return 0
  awk 'BEGIN{s=1} /^# >>> pdlcflow >>>$/{s=0} s==1{print} /^# <<< pdlcflow <<<$/{s=1}' "$f" > "$f.pdlctmp" && mv "$f.pdlctmp" "$f"; }
install_cli() {  # $1 = deploy dir (PDLCFLOW_HOME)
  local home_dir="$1" rc; rc="$(_rc_file)"
  mkdir -p "$PDLCFLOW_BIN_DIR"
  chmod +x "$home_dir/pdlcflow" 2>/dev/null || true
  ln -sf "$home_dir/pdlcflow" "$PDLCFLOW_BIN_DIR/pdlcflow"
  touch "$rc"; _rc_strip "$rc"
  { echo "# >>> pdlcflow >>>"
    echo "export PDLCFLOW_HOME=\"$home_dir\""
    echo "case \":\$PATH:\" in *\":$PDLCFLOW_BIN_DIR:\"*) ;; *) export PATH=\"$PDLCFLOW_BIN_DIR:\$PATH\" ;; esac"
    echo "# <<< pdlcflow <<<"; } >> "$rc"
  echo "$rc"
}

c "Installing pdlcflow → $DIR"
need curl
need docker
docker compose version >/dev/null 2>&1 || { echo "✗ Docker Compose v2 ('docker compose') is required." >&2; exit 1; }

mkdir -p "$DIR/postgres-init"
cd "$DIR"

c "↓ Downloading deploy files into $(pwd)"
curl -fsSLO "$BASE/docker-compose.yml"
curl -fsSLO "$BASE/.env.example"
for f in setup.sh update.sh uninstall.sh; do
  curl -fsSL "$BASE/$f" -o "$f" && chmod +x "$f"
done
curl -fsSL "$BASE/postgres-init/01-app-role.sh" -o postgres-init/01-app-role.sh
chmod +x postgres-init/01-app-role.sh  # Postgres execs init *.sh; curl -o drops the exec bit
curl -fsSL "$BASE/pdlcflow" -o pdlcflow && chmod +x pdlcflow

c "⚙  Configuring"
./setup.sh

c "🔗 Installing the 'pdlcflow' command (PDLCFLOW_HOME + PATH symlink)"
RC_FILE="$(install_cli "$(pwd)")"

if [ "$START" -eq 1 ]; then
  c "🚀 Starting the stack"
  docker compose up -d
  c "🗄  Applying the database schema"
  docker compose run --rm api uv run alembic upgrade head
  echo
  c "✓ pdlcflow is up."
  echo "   Studio:  http://localhost:8080"
  echo "   API:     http://localhost:8000/health"
else
  echo
  c "✓ Ready in $(pwd)."
  echo "   Start it with:  pdlcflow setup   (or: docker compose up -d)"
  echo "   Then migrate:   docker compose run --rm api uv run alembic upgrade head"
fi

echo
c "🧰 'pdlcflow' command installed → $PDLCFLOW_BIN_DIR/pdlcflow"
echo "   Open a new terminal (or: source \"$RC_FILE\"), then control the stack with:"
echo "     pdlcflow setup | start | stop | status | remove | wipe"

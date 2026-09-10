#!/usr/bin/env bash
# Bring up the local Docker stack for both repos: this one (FastAPI
# backend + strix engine) and the sibling strixui checkout (frontend).
# An nginx gateway serves them from one origin so session cookies work.
#
# Run from anywhere:
#   saas/dev.sh              # docker compose up --build
#   saas/dev.sh down         # stop and remove the stack
#   saas/dev.sh <args>       # passed through to docker compose
#
# Requires Docker Compose v2 and ../strixui next to this repo.
# Optional saas/backend/.env is loaded so LLM_API_KEY / GATEWAY_PORT
# (and any other exported vars) apply to compose interpolation.
# Env vars already exported in your shell still take precedence.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/docker-compose.yml"
BACKEND_ENV="$SCRIPT_DIR/backend/.env"
FRONTEND_REPO=""
if [ -d "$REPO_ROOT/../strixui" ]; then
  FRONTEND_REPO="$(cd "$REPO_ROOT/../strixui" && pwd)"
fi

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "docker-compose.yml not found at $COMPOSE_FILE" >&2
  exit 1
fi

if [ -z "$FRONTEND_REPO" ]; then
  echo "Frontend repo not found at $REPO_ROOT/../strixui." >&2
  echo "Clone strixui as a sibling of this repo, then retry." >&2
  exit 1
fi

if ! command -v docker >/dev/null; then
  echo "docker is required and must be on PATH." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 is required (the 'docker compose' plugin)." >&2
  exit 1
fi

if [ -f "$BACKEND_ENV" ]; then
  echo "==> Loading $BACKEND_ENV"
  set -a
  # shellcheck disable=SC1091
  source "$BACKEND_ENV"
  set +a
fi

export LLM_API_KEY="${LLM_API_KEY:-}"
export GATEWAY_PORT="${GATEWAY_PORT:-8095}"

cd "$REPO_ROOT"

if [ $# -eq 0 ]; then
  echo "==> Starting Docker stack"
  echo "    backend:  $REPO_ROOT"
  echo "    frontend: $FRONTEND_REPO"
  echo "    open:     http://localhost:${GATEWAY_PORT}"
  echo ""
  exec docker compose -f "$COMPOSE_FILE" up --build
fi

exec docker compose -f "$COMPOSE_FILE" "$@"

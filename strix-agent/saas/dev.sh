#!/usr/bin/env bash
# Starts the SaaS backend (FastAPI/uvicorn on :8000) and frontend (Vite on
# :5173) together, and stops both on Ctrl-C. Run from anywhere:
#   saas/dev.sh
#
# Real pentest execution (SAAS_ENABLE_REAL_SCAN=1) needs the optional
# `real-scan` dependency extra (the strix engine itself, Docker SDK, etc.) —
# plain `uv sync` does NOT install it, and running `uv sync` again later
# without the extra silently uninstalls it out from under a live server,
# since it's the same shared .venv.
#
# Rather than typing env vars every run (easy to forget — a plain
# `saas/dev.sh` then silently starts a mock-only backend, replacing a
# real-scan one you already had running), drop them in saas/backend/.env
# (gitignored) — this script auto-loads it before doing anything else.
# See saas/backend/.env.example for the two variables that matter here
# (SAAS_ENABLE_REAL_SCAN and, on macOS/Docker Desktop, DOCKER_HOST).
# Env vars exported in your shell still take precedence over the file.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

if [ -f "$BACKEND_DIR/.env" ]; then
  echo "==> Loading $BACKEND_DIR/.env"
  set -a
  # shellcheck disable=SC1091
  source "$BACKEND_DIR/.env"
  set +a
fi

command -v uv >/dev/null || { echo "uv is required (https://docs.astral.sh/uv/) — install it first." >&2; exit 1; }
command -v npm >/dev/null || { echo "npm is required — install Node.js first." >&2; exit 1; }

if [ "${SAAS_ENABLE_REAL_SCAN:-}" = "1" ]; then
  echo "==> Syncing backend dependencies (including the real-scan extra)"
  (cd "$BACKEND_DIR" && uv sync --extra real-scan)
  if [ -z "${DOCKER_HOST:-}" ]; then
    echo "    NOTE: DOCKER_HOST is not set. On macOS/Docker Desktop the SDK's" >&2
    echo "    default socket path is usually wrong — set it in" >&2
    echo "    $BACKEND_DIR/.env if the real scan fails to reach Docker" >&2
    echo "    (see .env.example for how to find the right value)." >&2
  fi
else
  echo "==> Syncing backend dependencies"
  (cd "$BACKEND_DIR" && uv sync)
fi

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "==> Installing frontend dependencies (first run)"
  (cd "$FRONTEND_DIR" && npm install)
fi

if command -v chflags >/dev/null; then
  # macOS-only: something (observed to recur even without any uv sync in
  # between — likely Spotlight/Time Machine indexing underscore-prefixed
  # files) intermittently sets UF_HIDDEN on uv's generated editable-install
  # `.pth` files. Python 3.12's site.py silently *skips* hidden .pth files,
  # which breaks `import strix` (and any other editable dependency) with no
  # error — it just isn't on sys.path. Clearing the flag is a harmless noop
  # when it's already unset.
  chflags nohidden "$BACKEND_DIR"/.venv/lib/python3.*/site-packages/*.pth 2>/dev/null || true
fi

if [ ! -f "$BACKEND_DIR/strix_saas.db" ]; then
  echo "==> Seeding demo data"
  (cd "$BACKEND_DIR" && uv run --no-sync python -m app.seed)
fi

PIDS=()
cleanup() {
  echo ""
  echo "==> Stopping..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

if [ "${SAAS_ENABLE_REAL_SCAN:-}" = "1" ]; then
  echo "==> Starting backend  → http://127.0.0.1:8000 (real scan ENABLED)"
else
  echo "==> Starting backend  → http://127.0.0.1:8000 (mock scan only — set SAAS_ENABLE_REAL_SCAN=1 to change that)"
fi
(cd "$BACKEND_DIR" && uv run --no-sync uvicorn app.main:app --reload --reload-dir app --port 8000) &
PIDS+=($!)

echo "==> Starting frontend → http://localhost:5173"
(cd "$FRONTEND_DIR" && npm run dev) &
PIDS+=($!)

echo ""
echo "Both are starting. Open http://localhost:5173 (use 'localhost', not 127.0.0.1)."
echo "Press Ctrl-C to stop both."
echo ""

wait

# Build context is the REPO ROOT (../.. from here), not saas/backend/ —
# saas/backend depends on the strix engine via a local editable path
# (`strix-agent = { path = "../..", editable = true }` in pyproject.toml),
# so both strix/ and saas/backend/ need to be present in the build.
#
# Build from the repo root:
#   docker build -f saas/backend/Dockerfile -t strix-backend .
#
# Real pentest execution (SAAS_ENABLE_REAL_SCAN=1 at runtime) needs the
# `real-scan` extra installed at build time — pass:
#   --build-arg INSTALL_REAL_SCAN=true
# It also needs a Docker socket available inside this container at runtime
# (the engine spawns sibling sandbox containers) — see docker-compose.yml.

FROM python:3.12-slim

# git: required at runtime for real scans — app/jobs.py clones the target
# repository (and, for PR reviews, fetches the PR ref) by shelling out to
# `git`, which the slim base image doesn't include. ca-certificates: needed
# for HTTPS clones (usually present already, but not guaranteed on slim).
RUN apt-get update && \
    apt-get install -y --no-install-recommends git ca-certificates && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

# Engine source + the root package metadata the editable install needs
# (hatchling reads pyproject.toml's `readme` field, and needs
# scripts/tui_sidecar_hook.py to exist to even evaluate its own
# early-return for editable installs — see that file).
COPY pyproject.toml README.md ./
COPY scripts/ ./scripts/
COPY strix/ ./strix/

# Backend app
COPY saas/backend/ ./saas/backend/

WORKDIR /app/saas/backend

ARG INSTALL_REAL_SCAN=false
RUN if [ "$INSTALL_REAL_SCAN" = "true" ]; then \
      uv sync --no-dev --extra real-scan; \
    else \
      uv sync --no-dev; \
    fi

ENV PATH="/app/saas/backend/.venv/bin:${PATH}"

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

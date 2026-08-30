# Capstone N3 Docker Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package the full Capstone N3 workspace as a reproducible, GitHub-safe Docker Compose application with a founder web UI, FastAPI backend, and optional Streamlit admin console.

**Architecture:** Build one non-root Python image shared by `api` and `admin`, plus one non-root Next.js standalone image for `web`. Compose connects the services on its default network, persists backend data in one named volume, exposes localhost-only ports, and defaults to deterministic offline mode.

**Tech Stack:** Docker Engine 27+, Docker Compose v2, Python 3.13 slim, uv 0.11.22, FastAPI/Uvicorn, Streamlit, Node 22 Alpine, Next.js 16 standalone, pytest 9.

**Spec:** `docs/superpowers/specs/2026-08-24-capstone-n3-docker-packaging-design.md`

## Global Constraints

- Preserve all existing dirty WIP; do not run reset, clean, checkout, or revert.
- Work on branch `codex/case-copilot-docker`, make reviewed logical local commits, and merge locally into `main` only after the complete verification gate.
- Do not push, deploy, publish images, or create a GitHub release.
- Default `FOUNDER_CASE_FIXTURE_MODE` to the exact value `deterministic_offline`.
- Publish ports on `127.0.0.1` only: web `3000`, API `8000`, admin `8501` by default.
- `admin` must use the exact Compose profile name `admin` and the same backend image as `api`.
- Mount the same named volume into `api` and `admin` at the exact path `/app/data`.
- Install backend groups `stage1b-light-ingest` and `founder-api`; exclude `dev` and `stage1a-rag-local`.
- Use Node `22` and Python `3.13`; use `package-lock.json` with `npm ci`.
- No API key, uploaded document, runtime database, `.venv`, `node_modules`, `.next`, cache, test temp data, or Docker image may enter Git or a Docker build context.
- Docker packaging must not alter evidence classification or turn `founder_statement`, `public_benchmark`, or `ai_scenario` into `source_fact`.
- Every implementation task ends with a task-scoped spec and quality review. The final state receives a whole-change review.

---

### Task 0: Docker executable RED packaging contract

**Files:**

- Create: `tests/smoke/test_docker_packaging.py`

**Interfaces:**

- Consumes: Docker Compose CLI v2 and repository files rooted two parents above this test.
- Produces: `_compose_config(*compose_args: str) -> dict[str, object]` and five executable acceptance tests used by Docker Tasks 1–4.

- [ ] **Step 1: Write the failing packaging tests**

Create the test module with these concrete contracts:

```python
from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _compose_config(*compose_args: str) -> dict[str, object]:
    completed = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(ROOT / "compose.yaml"),
            *compose_args,
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_compose_declares_full_workspace_contract() -> None:
    config = _compose_config("--profile", "admin")
    services = config["services"]
    assert set(services) == {"admin", "api", "web"}
    assert services["admin"]["profiles"] == ["admin"]
    assert services["web"]["depends_on"]["api"]["condition"] == "service_healthy"
    assert services["web"]["environment"]["FOUNDER_API_BASE_URL"] == "http://api:8000"
    assert services["api"]["image"] == services["admin"]["image"]
    assert services["api"]["volumes"][0]["target"] == "/app/data"
    assert services["admin"]["volumes"][0]["target"] == "/app/data"
    assert services["api"]["volumes"][0]["source"] == services["admin"]["volumes"][0]["source"]
    assert "healthcheck" in services["api"]
    assert "healthcheck" in services["web"]
    assert "healthcheck" in services["admin"]


def test_backend_image_is_reproducible_non_root_and_lean() -> None:
    dockerfile = _read("Dockerfile")
    assert "python:3.13-slim-bookworm" in dockerfile
    assert "ghcr.io/astral-sh/uv:0.11.22" in dockerfile
    assert "--group stage1b-light-ingest" in dockerfile
    assert "--group founder-api" in dockerfile
    assert "stage1a-rag-local" not in dockerfile
    assert "--group dev" not in dockerfile
    assert "USER app" in dockerfile
    assert '["investment-dd-api", "--all-interfaces", "--port", "8000"]' in dockerfile


def test_frontend_image_uses_locked_standalone_production_build() -> None:
    dockerfile = _read("frontend/founder/Dockerfile")
    next_config = _read("frontend/founder/next.config.ts")
    assert "FROM node:22-alpine" in dockerfile
    assert "npm ci" in dockerfile
    assert ".next/standalone" in dockerfile
    assert "USER nextjs" in dockerfile
    assert '["node", "server.js"]' in dockerfile
    assert 'output: "standalone"' in next_config


def test_docker_contexts_and_git_ignore_exclude_local_weight() -> None:
    root_dockerignore = _read(".dockerignore")
    web_dockerignore = _read("frontend/founder/.dockerignore")
    gitignore = _read(".gitignore")
    assert root_dockerignore.lstrip().startswith("**")
    assert "!src/**" in root_dockerignore
    assert web_dockerignore.lstrip().startswith("**")
    assert "!app/**" in web_dockerignore
    for pattern in ("/.uv-cache/", "/pytest*/", "/.pytest*/", "/codex_tmp_pytest/", "/tmp/"):
        assert pattern in gitignore


def test_docker_example_defaults_offline_and_contains_no_secret() -> None:
    example = _read(".env.docker.example")
    values = {
        key: value
        for line in example.splitlines()
        if line and not line.startswith("#") and "=" in line
        for key, value in [line.split("=", 1)]
    }
    assert values["FOUNDER_CASE_FIXTURE_MODE"] == "deterministic_offline"
    assert values["OPENAI_API_KEY"] == ""
    assert values["OPENAI_STARTUP_API_KEY"] == ""
    readme = _read("README.md")
    assert "docker compose up --build" in readme
    assert "docker compose --profile admin up --build" in readme
```

- [ ] **Step 2: Run the first RED test**

Run:

```powershell
uv run --offline --no-sync --no-default-groups --group dev pytest tests/smoke/test_docker_packaging.py::test_compose_declares_full_workspace_contract -q
```

Expected: FAIL because `compose.yaml` does not exist.

- [ ] **Step 3: Run the complete RED module**

Run:

```powershell
uv run --offline --no-sync --no-default-groups --group dev pytest tests/smoke/test_docker_packaging.py -q
```

Expected: five failures naming the missing Docker packaging artifacts or unmet ignore/config contracts.

- [ ] **Step 4: Commit the RED contract**

Stage only `tests/smoke/test_docker_packaging.py`, verify the staged diff, and commit with message `test: define docker packaging contract`.

- [ ] **Step 5: Review the RED test quality**

Create a task-scoped review package from the Task 0 base through its commit. The reviewer must confirm both that the tests match the approved design and that each failure is caused by missing production configuration rather than a broken test harness. Append `Docker Task 0: complete` with the commit hash and review verdict to the SDD ledger.

### Task 1: Docker Git and build-context boundaries

**Files:**

- Create: `.dockerignore`
- Create: `frontend/founder/.dockerignore`
- Modify: `.gitignore`
- Test: `tests/smoke/test_docker_packaging.py`

**Interfaces:**

- Consumes: exact file paths asserted by Docker Task 0.
- Produces: strict allowlist contexts for the backend and frontend builds plus durable Git exclusions for existing multi-gigabyte local artifacts.

- [ ] **Step 1: Confirm the focused test is RED**

Run:

```powershell
uv run --offline --no-sync --no-default-groups --group dev pytest tests/smoke/test_docker_packaging.py::test_docker_contexts_and_git_ignore_exclude_local_weight -q
```

Expected: FAIL because both `.dockerignore` files are absent and `.gitignore` lacks the required patterns.

- [ ] **Step 2: Add the backend allowlist**

Create `.dockerignore` with:

```dockerignore
**
!Dockerfile
!pyproject.toml
!uv.lock
!README.md
!src/
!src/**
```

- [ ] **Step 3: Add the frontend allowlist**

Create `frontend/founder/.dockerignore` with:

```dockerignore
**
!Dockerfile
!package.json
!package-lock.json
!next.config.ts
!next-env.d.ts
!tsconfig.json
!app/
!app/**
!components/
!components/**
!lib/
!lib/**
!public/
!public/**
!scripts/
!scripts/**
```

- [ ] **Step 4: Harden Git ignores without touching tracked assets**

Append these root-anchored patterns to `.gitignore`:

```gitignore

# Docker/GitHub packaging: local dependency caches and verification workspaces.
/.uv-cache/
/.uv-cache-*/
/.pytest*/
/pytest*/
/codex_tmp_pytest/
/tmp/
/task*_data/
/root_verify_*/
/smoke_tmp_*/
```

Do not add a blanket `/artifacts/` rule because tracked UI evidence exists beneath that directory.

- [ ] **Step 5: Run the focused GREEN test and ignore probes**

Run:

```powershell
uv run --offline --no-sync --no-default-groups --group dev pytest tests/smoke/test_docker_packaging.py::test_docker_contexts_and_git_ignore_exclude_local_weight -q
git check-ignore -v .uv-cache .uv-cache-docker pytest_env_tmp_task11_current_gates codex_tmp_pytest tmp
```

Expected: pytest PASS; every probe is ignored by a root `.gitignore` rule.

- [ ] **Step 6: Commit the context boundaries**

Stage only `.dockerignore`, `frontend/founder/.dockerignore`, and `.gitignore`, verify the staged diff, and commit with message `build: bound docker and git contexts`.

- [ ] **Step 7: Review the Task 1 commit**

Review the exact Task 1 commit range. After spec and quality approval, append `Docker Task 1: complete` with the commit hash and verdict to the ledger.

### Task 2: Docker shared Python backend image

**Files:**

- Create: `Dockerfile`
- Test: `tests/smoke/test_docker_packaging.py`

**Interfaces:**

- Consumes: root allowlist context from Docker Task 1 and project entry point `investment-dd-api`.
- Produces: local image tag `capstone-n3-backend:local`, default API command, Streamlit-capable runtime, `/app/data`, and non-root user `app` with UID 10001.

- [ ] **Step 1: Confirm the focused test is RED**

Run:

```powershell
uv run --offline --no-sync --no-default-groups --group dev pytest tests/smoke/test_docker_packaging.py::test_backend_image_is_reproducible_non_root_and_lean -q
```

Expected: FAIL because `Dockerfile` does not exist.

- [ ] **Step 2: Create the backend Dockerfile**

Create `Dockerfile` with this runtime contract:

```dockerfile
# syntax=docker/dockerfile:1.7

FROM ghcr.io/astral-sh/uv:0.11.22 AS uv-bin
FROM python:3.13-slim-bookworm AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH=/app/.venv/bin:$PATH \
    DDA_DATA_DIR=/app/data

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        fonts-dejavu-core \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=uv-bin /uv /uvx /bin/
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-default-groups \
      --group stage1b-light-ingest \
      --group founder-api \
      --no-install-project

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-default-groups \
      --group stage1b-light-ingest \
      --group founder-api \
      --no-editable \
    && useradd --create-home --uid 10001 app \
    && mkdir -p /app/data \
    && chown -R app:app /app/data

USER app
EXPOSE 8000 8501
CMD ["investment-dd-api", "--all-interfaces", "--port", "8000"]
```

- [ ] **Step 3: Run the focused GREEN test**

Run:

```powershell
uv run --offline --no-sync --no-default-groups --group dev pytest tests/smoke/test_docker_packaging.py::test_backend_image_is_reproducible_non_root_and_lean -q
```

Expected: PASS.

- [ ] **Step 4: Commit the backend image**

Stage only `Dockerfile`, verify the staged diff, and commit with message `build: add shared backend image`.

- [ ] **Step 5: Review the Task 2 commit**

Review `Dockerfile` against the spec, including native report dependencies, non-root execution, absence of heavy RAG/dev groups, and correct all-interface binding inside the container. After approval, append `Docker Task 2: complete` with the commit hash and verdict to the ledger.

### Task 3: Docker Next.js image and Compose topology

**Files:**

- Create: `frontend/founder/Dockerfile`
- Create: `compose.yaml`
- Modify: `frontend/founder/next.config.ts`
- Test: `tests/smoke/test_docker_packaging.py`

**Interfaces:**

- Consumes: shared backend image contract from Docker Task 2, `FOUNDER_API_BASE_URL`, `NEXT_PUBLIC_ADMIN_CONSOLE_URL`, and `FOUNDER_CASE_FIXTURE_MODE` already read by the application.
- Produces: image `capstone-n3-web:local`; services `web`, `api`, and profile-gated `admin`; volume `case-data`; localhost-only ports; three health checks.

- [ ] **Step 1: Confirm the frontend and Compose tests are RED**

Run:

```powershell
uv run --offline --no-sync --no-default-groups --group dev pytest tests/smoke/test_docker_packaging.py::test_frontend_image_uses_locked_standalone_production_build tests/smoke/test_docker_packaging.py::test_compose_declares_full_workspace_contract -q
```

Expected: FAIL because the frontend Dockerfile and Compose file do not exist and standalone output is not enabled.

- [ ] **Step 2: Enable standalone output**

Add this exact property inside `nextConfig` in `frontend/founder/next.config.ts`:

```typescript
output: "standalone",
```

Preserve the pre-existing dirty-WIP line `distDir: process.env.FOUNDER_NEXT_DIST_DIR?.trim() || ".next"`; it isolates local dev/build caches and is not reverted by this task. Because both properties occupy the same existing file, the Task 3 commit records that preserved line together with the new standalone property.

- [ ] **Step 3: Create the frontend Dockerfile**

Create `frontend/founder/Dockerfile`:

```dockerfile
# syntax=docker/dockerfile:1.7

FROM node:22-alpine AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

FROM node:22-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
ARG NEXT_PUBLIC_ADMIN_CONSOLE_URL=http://localhost:8501/
ENV NEXT_PUBLIC_ADMIN_CONSOLE_URL=$NEXT_PUBLIC_ADMIN_CONSOLE_URL
COPY --from=dependencies /app/node_modules ./node_modules
COPY . .
RUN npm run build \
    && cp .next/server/app/index.html .next/standalone/.next/server/app/index.html

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
RUN addgroup --system --gid 10001 nodejs \
    && adduser --system --uid 10001 nextjs
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
```

The post-build copy preserves the existing injected direction contract inside the standalone server tree.

- [ ] **Step 4: Create the Compose application**

Create `compose.yaml` with this exact service topology:

```yaml
name: capstone-n3

services:
  api:
    image: capstone-n3-backend:local
    build:
      context: .
      dockerfile: Dockerfile
    init: true
    environment:
      DDA_DATA_DIR: /app/data
      DDA_RUNTIME_PROFILE: ${DDA_RUNTIME_PROFILE:-local}
      DDA_LANGSMITH_TRACING: ${DDA_LANGSMITH_TRACING:-false}
      DDA_AUDIT_REQUIRED: ${DDA_AUDIT_REQUIRED:-true}
      FOUNDER_CASE_FIXTURE_MODE: ${FOUNDER_CASE_FIXTURE_MODE:-deterministic_offline}
      OPENAI_API_KEY: ${OPENAI_API_KEY:-}
      OPENAI_STARTUP_API_KEY: ${OPENAI_STARTUP_API_KEY:-}
    volumes:
      - case-data:/app/data
    ports:
      - "127.0.0.1:${API_PORT:-8000}:8000"
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=5)"]
      interval: 10s
      timeout: 5s
      retries: 12
      start_period: 20s

  web:
    image: capstone-n3-web:local
    build:
      context: ./frontend/founder
      dockerfile: Dockerfile
      args:
        NEXT_PUBLIC_ADMIN_CONSOLE_URL: ${NEXT_PUBLIC_ADMIN_CONSOLE_URL:-http://localhost:8501/}
    init: true
    environment:
      FOUNDER_API_BASE_URL: http://api:8000
      FOUNDER_CASE_FIXTURE_MODE: ${FOUNDER_CASE_FIXTURE_MODE:-deterministic_offline}
    depends_on:
      api:
        condition: service_healthy
    ports:
      - "127.0.0.1:${WEB_PORT:-3000}:3000"
    healthcheck:
      test: ["CMD", "node", "-e", "fetch('http://127.0.0.1:3000/').then((response) => { if (!response.ok) process.exit(1); }).catch(() => process.exit(1))"]
      interval: 10s
      timeout: 5s
      retries: 12
      start_period: 20s

  admin:
    image: capstone-n3-backend:local
    profiles: ["admin"]
    init: true
    command:
      - streamlit
      - run
      - src/due_diligence_agent/presentation/streamlit/app.py
      - --server.address
      - 0.0.0.0
      - --server.port
      - "8501"
      - --server.headless
      - "true"
      - --browser.gatherUsageStats
      - "false"
    environment:
      DDA_DATA_DIR: /app/data
      DDA_RUNTIME_PROFILE: ${DDA_RUNTIME_PROFILE:-local}
      DDA_LANGSMITH_TRACING: ${DDA_LANGSMITH_TRACING:-false}
      DDA_AUDIT_REQUIRED: ${DDA_AUDIT_REQUIRED:-true}
      FOUNDER_CASE_FIXTURE_MODE: ${FOUNDER_CASE_FIXTURE_MODE:-deterministic_offline}
      OPENAI_API_KEY: ${OPENAI_API_KEY:-}
      OPENAI_STARTUP_API_KEY: ${OPENAI_STARTUP_API_KEY:-}
    volumes:
      - case-data:/app/data
    ports:
      - "127.0.0.1:${ADMIN_PORT:-8501}:8501"
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=5)"]
      interval: 10s
      timeout: 5s
      retries: 12
      start_period: 30s

volumes:
  case-data:
```

- [ ] **Step 5: Run focused GREEN checks**

Run:

```powershell
uv run --offline --no-sync --no-default-groups --group dev pytest tests/smoke/test_docker_packaging.py::test_frontend_image_uses_locked_standalone_production_build tests/smoke/test_docker_packaging.py::test_compose_declares_full_workspace_contract -q
docker compose -f compose.yaml config --quiet
docker compose -f compose.yaml --profile admin config --quiet
npm --prefix frontend/founder run typecheck
npm --prefix frontend/founder test
npm --prefix frontend/founder run build
```

Expected: every command exits 0.

- [ ] **Step 6: Commit the frontend and Compose topology**

Stage only `frontend/founder/Dockerfile`, `frontend/founder/next.config.ts`, and `compose.yaml`, verify the staged diff, and commit with message `build: compose full founder workspace`.

- [ ] **Step 7: Review the Task 3 commit**

Review the exact Task 3 commit and focused test evidence. Confirm that `api` and `admin` share an image and volume, the admin profile is optional, standalone contains the direction contract, and only localhost ports are published. After approval, append `Docker Task 3: complete` with the commit hash and verdict to the ledger.

### Task 4: Docker safe operator handoff and runtime proof

**Files:**

- Create: `.env.docker.example`
- Modify: `README.md`
- Test: `tests/smoke/test_docker_packaging.py`

**Interfaces:**

- Consumes: Compose commands and environment keys produced by Docker Task 3.
- Produces: copy-safe offline defaults, Russian operator instructions, successful container smokes, exact image sizes, and final review evidence.

- [ ] **Step 1: Confirm the handoff test is RED**

Run:

```powershell
uv run --offline --no-sync --no-default-groups --group dev pytest tests/smoke/test_docker_packaging.py::test_docker_example_defaults_offline_and_contains_no_secret -q
```

Expected: FAIL because `.env.docker.example` and Docker README instructions do not exist.

- [ ] **Step 2: Add the safe environment example**

Create `.env.docker.example`:

```dotenv
# Copy to .env for local overrides. Never commit the resulting .env file.
COMPOSE_PROJECT_NAME=capstone-n3
WEB_PORT=3000
API_PORT=8000
ADMIN_PORT=8501

# Safe no-cost default. Change to live only when credentials are configured.
FOUNDER_CASE_FIXTURE_MODE=deterministic_offline
DDA_RUNTIME_PROFILE=local
DDA_LANGSMITH_TRACING=false
DDA_AUDIT_REQUIRED=true
NEXT_PUBLIC_ADMIN_CONSOLE_URL=http://localhost:8501/

# Optional live-mode credentials. Keep values empty in this tracked example.
OPENAI_API_KEY=
OPENAI_STARTUP_API_KEY=
```

- [ ] **Step 3: Add Russian Docker instructions to README**

Add a `## Docker Compose` section covering:

```powershell
Copy-Item .env.docker.example .env
docker compose up --build
docker compose --profile admin up --build
docker compose down
```

Document URLs `http://127.0.0.1:3000/`, `http://127.0.0.1:8000/docs`, and `http://127.0.0.1:8501/`; explain offline/live modes, named-volume persistence, `docker compose down -v` as a deliberately destructive data-removal command that is not part of normal shutdown, and that Docker images must not be committed to GitHub.

- [ ] **Step 4: Run the complete static GREEN gate**

Run:

```powershell
uv run --offline --no-sync --no-default-groups --group dev pytest tests/smoke/test_docker_packaging.py -q
docker compose -f compose.yaml config --quiet
docker compose -f compose.yaml --profile admin config --quiet
```

Expected: all five pytest tests PASS; both Compose validations exit 0.

- [ ] **Step 5: Build and smoke the default application**

Run sequentially on the resource-constrained owner laptop:

```powershell
docker compose -f compose.yaml build api
docker compose -f compose.yaml build web
docker compose -f compose.yaml up -d api web
docker compose -f compose.yaml ps
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-WebRequest http://127.0.0.1:3000/ -UseBasicParsing
```

Expected: `api` and `web` become healthy; API returns `status=ok`; the web request returns HTTP 200.

- [ ] **Step 6: Smoke the optional admin profile**

Run:

```powershell
docker compose -f compose.yaml --profile admin up -d admin
docker compose -f compose.yaml --profile admin ps
Invoke-WebRequest http://127.0.0.1:8501/_stcore/health -UseBasicParsing
```

Expected: `admin` becomes healthy and the health request returns HTTP 200.

- [ ] **Step 7: Measure exact artifacts and stop containers safely**

Run:

```powershell
docker image inspect capstone-n3-backend:local capstone-n3-web:local --format '{{.RepoTags}} {{.Size}}'
docker compose -f compose.yaml --profile admin down
```

Record byte sizes and human-readable MiB/GiB in the ledger and final handoff. Do not use `down -v`; preserve the named volume.

- [ ] **Step 8: Update the durable handoff and commit operator documentation**

Update `docs/handoffs/2026-08-24-capstone-n3-docker-packaging-handoff.md` with exact task commits, tests, image sizes, remaining risks, and resume commands. Stage `.env.docker.example`, `README.md`, the approved spec, plan, and handoff; verify the staged diff; commit with message `docs: hand off docker workspace`.

- [ ] **Step 9: Review the Task 4 commit**

Review the exact Task 4 commit, documentation commands, measured evidence, and secret-free example. After approval, append `Docker Task 4: complete` with the commit hash and verdict to the ledger.

## Final integration gate

- [ ] Generate a whole-branch review package covering the Docker Task 0 base through Task 4 HEAD.
- [ ] Run the most capable available whole-change review, including deferred baseline failures and every ledger ruling.
- [ ] If required, dispatch one fix wave, commit it, and run one scoped re-review.
- [ ] Confirm the main worktree is clean and merge locally only through a non-destructive reviewed merge; do not push.

## Plan self-review

- Spec coverage: every architecture, safety, persistence, size, startup, and verification requirement maps to Docker Tasks 0–4.
- Placeholder scan: the plan contains no deferred implementation placeholders; commands and file contents are concrete.
- Interface consistency: `compose.yaml`, image tags, ports, profile, environment keys, named volume, and test assertions use the same exact names throughout.
- Git workflow: the owner explicitly authorized a feature branch, reviewed local commits, and a local merge into `main` after verification. Push and image publication remain separate external actions.

# Capstone N3 Docker Packaging Design

**Date:** 2026-08-24
**Status:** Approved by the owner in chat
**Scope:** Full local product: Founder Workspace, Founder API, and optional Streamlit Admin Console

## Outcome

Package Capstone N3 as a reproducible local Docker Compose application that can be stored in GitHub without committing generated data, caches, secrets, dependencies, or Docker images.

The owner must be able to start the founder-facing product with:

```powershell
docker compose up --build
```

The optional operator console must start with:

```powershell
docker compose --profile admin up --build
```

## Architecture

The Compose application has three services and two images:

| Service | Image | Purpose | Host port |
| --- | --- | --- | --- |
| `web` | Next.js production image | Founder-facing Russian product UI and same-origin API proxy | `3000` |
| `api` | Shared Python backend image | FastAPI Founder API | `8000` |
| `admin` | Same Python backend image as `api` | Optional Streamlit operator console | `8501` |

`admin` is placed behind the Compose profile `admin`. It reuses the exact backend image instead of creating a duplicate image. `api` and `admin` mount the same named volume at `/app/data`, matching the current native launcher’s shared-data model.

The frontend sends server-side proxy traffic to `http://api:8000`. Browser navigation to the admin console uses `http://localhost:8501/` by default. All published ports bind to `127.0.0.1` so the local product is not exposed to the LAN accidentally.

## Runtime modes

The Docker package defaults to:

```text
FOUNDER_CASE_FIXTURE_MODE=deterministic_offline
```

This makes the repository testable without credentials or paid model calls. Live behavior remains available through a user-created `.env` file. `.env.docker.example` contains empty secret fields only; no API key is baked into an image, Compose file, Git history, or documentation.

The backend image installs `stage1b-light-ingest` and `founder-api`. It deliberately excludes the `dev` and `stage1a-rag-local` groups so pytest tooling, sentence-transformers, FAISS, torch, and local model files do not inflate the runtime image.

## Build boundaries

The root `.dockerignore` uses an allowlist and sends only the backend build inputs:

- `Dockerfile`
- `pyproject.toml`
- `uv.lock`
- `README.md`
- `src/**`

`frontend/founder/.dockerignore` independently allowlists the Next.js build inputs. Local `node_modules`, `.next`, browser artifacts, temporary tests, documents, runtime databases, and uploaded case materials never enter either Docker build context.

The backend image uses Python 3.13 and a pinned `uv` binary. The frontend uses Node 22, `npm ci`, a multi-stage build, and Next.js standalone output. Both runtime containers run as non-root users.

## Persistence and product boundaries

The named Docker volume contains runtime case data and uploaded documents. It is not part of either image and is not committed to GitHub.

Docker packaging must not change evidence semantics. In particular, `founder_statement`, `public_benchmark`, and `ai_scenario` never become `source_fact` automatically. Scenario provenance, ranges, formulas, dependencies, and validation plans remain application-level contracts and are neither rewritten nor pre-populated by Docker configuration.

## Health and startup behavior

- `api` is healthy only when `GET /health/live` succeeds.
- `web` waits for the API health check before starting.
- `web` has its own HTTP health check.
- `admin`, when selected, has a Streamlit health check.
- Compose stops and restarts each service independently; no supervisor-style monolithic container is introduced.

## GitHub and size targets

Current Git-tracked content is approximately 32.73 MiB. The expected GitHub repository remains roughly 33–50 MiB after the Docker files are added. Existing multi-gigabyte runtime and test artifacts must remain ignored.

Acceptance targets:

- backend Docker build context below 100 MiB;
- frontend Docker build context below 100 MiB;
- no secret, runtime data, uploaded document, virtual environment, dependency tree, test temp directory, or Docker image in Git;
- exact built-image sizes reported from `docker image inspect` after a successful local build.

Docker images are distribution artifacts, not Git repository files. Publishing them to GitHub Container Registry is outside this task and requires a separate explicit request because it is an external publish action.

## Verification

Verification proceeds from cheap to expensive:

1. RED packaging contract tests.
2. Focused GREEN tests for ignore rules, backend image, frontend image, Compose topology, and safe example environment.
3. `docker compose config` for default and `admin` profiles.
4. Production frontend tests, typecheck, and build.
5. Docker image build.
6. Container health checks and HTTP smoke tests for ports 3000, 8000, and optionally 8501.
7. Image-size and build-context measurement.

The owner subsequently authorized a normal local Git workflow: create a feature branch, make reviewed logical commits, and merge locally into `main` after the complete verification gate. Push, deploy, image publication, cleanup, reset, checkout of user files, and revert remain unauthorized.

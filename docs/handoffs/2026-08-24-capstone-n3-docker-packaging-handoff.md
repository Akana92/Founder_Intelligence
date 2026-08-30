# Capstone N3 Docker Packaging Handoff

**Updated:** 2026-08-25
**Status:** Docker Tasks 0–4, Case Copilot source curation, clean-clone application/Compose gates, and final whole-branch review are complete and approved; local merge is intentionally blocked by preserved dirty `main` WIP
**Worktree:** `C:\Users\Akana\.codex\worktrees\6e2b\Capstone N3`
**Branch:** `codex/case-copilot-docker`
**Base:** `fa4405a`

## Owner intent

Package the complete current product for GitHub and local Docker Compose use:

- Next.js Founder Workspace;
- FastAPI Founder API;
- optional Streamlit Admin Console through the Compose profile `admin`.

The owner authorized a normal local Git workflow: feature branch, logical reviewed commits, and a local merge into `main` after the complete test gate. On 2026-08-25 the owner explicitly reaffirmed that local commits are allowed whenever the agent judges them safe and necessary for the project. Do not push, deploy, publish images, reset, clean, or revert without a new explicit request.

## Source of truth

Read these files completely before continuing:

1. `docs/superpowers/specs/2026-08-24-capstone-n3-docker-packaging-design.md`
2. `docs/superpowers/plans/2026-08-24-capstone-n3-docker-packaging.md`
3. `docs/handoffs/2026-08-22-case-copilot-v1-new-chat-prompt.md`
4. The two Case Copilot source-of-truth specs named by that earlier handoff.

Use `superpowers:subagent-driven-development`, `superpowers:test-driven-development`, and review gates. Do not repeat already accepted Case Copilot Tasks 1–9.

## Current state

- The original large dirty Case Copilot WIP is preserved in this worktree.
- The worktree was detached at `fa4405a`; it is now attached to `codex/case-copilot-docker`.
- Docker Desktop was safely updated in place from `4.33.1` to `4.88.0.237115`; Docker client/server are `29.7.2`, Compose is `5.4.0`. The daemon passed the final runtime gate and was then intentionally stopped to release laptop memory.
- Docker Tasks 0–3 are implemented, committed, and independently reviewed:
  - `06c2193e` — Docker packaging RED contract tests;
  - `6515f2e9` — bounded Docker and Git contexts;
  - `19769961` — shared non-root backend image;
  - `579883d7` — standalone web image and three-service Compose topology.
- Approved architecture is present: two images, three services, shared backend image and named data volume, offline mode by default, localhost-only ports.
- Task 4 static operator work is complete: `.env.docker.example` exists with offline defaults and empty live keys; `README.md` has Russian Docker Compose instructions.
- Task 4 runtime work is complete: the backend and web images built sequentially; API, web, and optional admin reached `healthy`; all three localhost requests returned the expected successful response.
- Test containers were stopped with `docker compose ... down` without `-v`. Both images and the named volume `capstone-n3_case-data` remain available; Docker Desktop is stopped after the successful final smoke.

## 2026-08-25 restart recovery

- Windows booted at `2026-08-25 00:00:46` local time.
- System events `1074`, `109`, `577`, `6006`, and `6005` show an orderly system-initiated restart through the Kernel API. Kernel-Boot event `20` records the previous shutdown and boot as successful.
- No events `41`, `6008`, or BugCheck `1001` were found in the inspected window, so the evidence does not indicate power loss, a BSOD, or an abrupt kernel crash.
- Docker Desktop 4.33.1 started at approximately `23:58:42`, remained in `starting`, and could not bring its WSL internal services online. Its logs show the WSL context being cancelled at `00:00:13`, immediately before Windows recorded the restart request at `00:00:16`.
- Docker logs contain no observed install action or request to reboot Windows. The available logs prove temporal overlap but do not identify the exact application or service that called the system restart API.
- At that checkpoint, heavy Docker work was intentionally paused until the machine was stable. The later successful recovery and runtime proof are recorded below.

## Exact next action

Do not repeat Docker Tasks 0–4 or accepted Case Copilot Tasks 1–11. Continue only from this closing boundary:

1. Recheck branch `codex/case-copilot-docker`, current HEAD, and this handoff.
2. Treat the current feature branch as the verified delivery checkpoint. The final review of all `224` committed changed files returned APPROVE with zero findings.
3. Keep `D:\Agents\Projects\Capstone N3` on `main` untouched. It remains at base `fa4405a` with more than one hundred tracked modifications overlapping this feature branch plus untracked WIP; direct merge, checkout, stash, reset, clean, or force-update is unsafe.
4. If the owner later wants `main` updated, first design a separate reviewed preservation/reconciliation workflow for that dirty WIP. Do not infer permission to discard or overwrite it from the general authorization for local commits.
5. Do not push, deploy, publish images, or enable configured-live external providers without a new explicit request.

## Task 4 static evidence

- RED: `uv run --offline --no-sync --no-default-groups --group dev pytest tests/smoke/test_docker_packaging.py::test_docker_example_defaults_offline_and_contains_no_secret -q` failed because `.env.docker.example` did not exist. The first attempt was blocked by Windows ACL on the global `uv` cache, then the same test was rerun with `UV_CACHE_DIR` inside the worktree.
- GREEN: `uv run --offline --no-sync --no-default-groups --group dev pytest tests/smoke/test_docker_packaging.py -q -p no:cacheprovider` passed: `5 passed in 0.56s` on independent review and `5 passed in 0.54s` on the fresh post-runtime rerun. The fresh rerun used worktree-local `UV_CACHE_DIR` because the global Windows `uv` cache remains ACL-blocked.
- GREEN: `docker compose -f compose.yaml config --quiet` exited `0`.
- GREEN: `docker compose -f compose.yaml --profile admin config --quiet` exited `0`.
- Runtime proof is recorded below.

## Task 4 runtime completion

- The owner approved the safe in-place Docker Desktop update. The exact official installer `4.88.0.237115` was downloaded, Authenticode-verified as signed by Docker Inc, and its SHA-256 matched the published checksum: `53bd0193c96dfa81a25c5f4ae4f6d5143c4165d282287630c72ea5fe6025007b`.
- A pre-update settings/metadata backup was created at `C:\Users\Akana\AppData\Local\Temp\capstone-n3-docker-update-backup-20260825`. The installer completed with exit code `0`; no uninstall, reset, WSL unregister, or Docker-data deletion was performed.
- Docker Desktop `4.88.0.237115` started successfully outside the sandbox. Fresh version evidence: Docker client `29.7.2`, server `29.7.2`, Compose `5.4.0`, Desktop status `running`.
- Sequential builds passed:
  - `docker compose -f compose.yaml build api` produced `capstone-n3-backend:local` (`sha256:c96d96ed712dcac549d49aa376a89adf4aaaacd721b78d3f8da6f196e94ecfa5`);
  - `docker compose -f compose.yaml build web` completed the Next.js production build, TypeScript check, and direction-contract verification, producing `capstone-n3-web:local` (`sha256:bad0ad52c0ed56a40e515c248ee16edb4e31daecdd31f76bf06eb128690f86bf`).
- Port `8000` was already owned by the unrelated running container `smartuni-app`. It was not stopped or modified. The runtime smoke used the supported override `API_PORT=8180`; the image still listens on internal port `8000`, and the documented default remains `8000` when free.
- Default-stack smoke passed: API and web both reached `healthy`; `http://127.0.0.1:8180/health/live` returned `{"status":"ok"}` and `http://127.0.0.1:3000/` returned HTTP `200` with HTML.
- Optional-admin smoke passed: admin reached `healthy`; `http://127.0.0.1:8501/_stcore/health` returned HTTP `200` and body `ok`.
- Port inspection proved localhost-only publication: web `127.0.0.1:3000`, API `127.0.0.1:8180`, admin `127.0.0.1:8501`. Image/container inspection proved non-root users `nextjs` for web and `app` for API/admin. API and admin both mounted `capstone-n3_case-data:/app/data`.
- Exact local image sizes from Docker:
  - backend: `1,053,887,251` bytes (`1005.1 MiB`, `0.98 GiB`);
  - web: `233,392,101` bytes (`222.6 MiB`, `0.22 GiB`);
  - combined local image size: `1,287,279,352` bytes (about `1.20 GiB`). These images are local runtime artifacts and must not be committed to GitHub.
- `docker compose -f compose.yaml --profile admin down` stopped and removed only the test containers/network. It did not use `-v`; subsequent inspection confirmed both images and `capstone-n3_case-data` still exist.

## Final clean-clone evidence

- A local no-hardlinks clone was verified at `C:\Users\Akana\AppData\Local\Temp\capstone-n3-clean-614863a4886345b0bbff5be3fec7038d`, commit `fd68f9ed53e05bf0614c2b5d468956fdd6d17bd2`. It remained Git-clean after dependency installation, tests, production builds, and the Compose runtime smoke.
- The tracked checkout is `37,219,847` bytes (`35.5 MiB`). The local Git pack is about `42.37 MiB`. `node_modules`, caches, runtime evidence, case data, and Docker images are ignored/runtime-only and are not part of the GitHub source checkout.
- Exact approved Case Copilot backend gate: `201 passed in 34.05s`.
- Runtime/browser/launcher gate: `79 passed in 6.89s`.
- Docker packaging test: `5 passed`; default and `admin` Compose configuration checks both exited `0`.
- Pinned Ruff passed over `src tests`.
- Mypy passed all `252` local source files with only `import-not-found` and the consequent `unused-ignore` diagnostics disabled because this lightweight environment intentionally omits optional `sentence-transformers`, `faiss`, and `yfinance` packages. No local type error remained.
- Founder frontend `npm test`, `npm run typecheck`, and `npm run lint` passed. The clean-clone web image build reran and passed the Next.js production build, TypeScript check, direction-contract injection, and direction-contract verification.
- Sequential clean-clone image builds passed. With `API_PORT=8180`, API, web, and admin all reached `healthy`; API returned HTTP `200` with `{"status":"ok"}`, web returned HTTP `200` with Russian founder UI content, and admin returned HTTP `200` with body `ok`.
- After proof, `docker compose --profile admin down` was run without `-v`, then Docker Desktop was stopped. Images and the named data volume were preserved.
- Configured-live OpenAI/public-provider execution remains explicitly unverified because this gate used no live credential or allowed external egress. Deterministic/offline Case Copilot and consent/fail-closed public-research boundaries are verified.
- Final whole-branch code/spec/security review covered all `224` committed changed files in `fa4405a...fd68f9e` and returned APPROVE: `0` CRITICAL, `0` HIGH, `0` MEDIUM, `0` LOW findings.

## Docker/WSL recovery guidance

Official Docker documentation requires WSL `2.1.5` or later for the WSL 2 backend and recommends the latest WSL; this machine has WSL `2.7.12.0`, and the Docker WSL distribution starts successfully outside the sandbox. Official Microsoft documentation identifies `wsl --shutdown`, `wsl --version`, `wsl --status`, `wsl -l -v`, and `wsl --update` as the supported WSL verification/update commands.

The recovery completed successfully through step 2 below. Keep this order only for future recurrence:

1. Keep Docker Desktop fully closed until the owner approves a system-level update.
2. Update Docker Desktop in place through the official installer/UI to the current stable Windows build, preserving the existing installation and Docker data. Do not uninstall, use `Clean up data`, use `Reset to factory defaults`, or run `wsl --unregister`.
3. Start Docker Desktop outside the Codex sandbox and wait for the daemon. If it becomes healthy, continue runtime verification.
4. If the updated Desktop still fails, close it, run the supported `wsl --update` and `wsl --shutdown` path only with owner approval, then retry once.
5. If that still fails, gather Docker diagnostics before considering any repair. Do not hand-edit Docker's app-owned settings while an official in-place update remains available.

## Product boundary that must survive packaging

`founder_statement`, `public_benchmark`, and `ai_scenario` never become `source_fact` automatically. Scenario metrics continue to expose provenance, range, formula, dependencies, and validation plan. Docker configuration must not embed runtime case data or alter those semantics.

## Completion evidence and owner test command

Docker task commits already on the feature branch:

- `06c2193e` — RED packaging contracts;
- `6515f2e9` — bounded contexts;
- `19769961` — backend image;
- `579883d7` — web image and Compose;
- `714717f2`, `c21f61ca`, `c715e28c`, `3f579ce2`, `9718501f`, `69fdca1b` — Task 4 operator/recovery handoff checkpoints.
- `a58bb5c` — Task 4 measured runtime proof and owner test command.
- `c5fd00ca` — reviewed Docker handoff and occupied-port guidance.
- `c3b4402e` — provenance-safe Case Copilot backend.
- `088e1387` — readable Russian Founder Workspace.
- `e33b05c3` — founder launcher smoke contracts.
- `c7d7e6a3`, `3ac7391f` — founder-readable launch-pack copy and safe download names.
- `fd947262`, `1c4c4950` — curated runtime scripts and fail-closed deferred-evidence contract.
- `210f8d43` — durable Case Copilot specs/plans/handoffs/verification source set.
- `15bc2f4d`, `1c0f820a` — self-contained PDF differentiation fixture and formatting repair.
- `fd68f9ed` — clean-clone portable runtime/smoke tests.

The local merge is intentionally not performed. Source curation and the fresh-clone runtime gate are complete, but the separate `main` worktree still contains extensive tracked and untracked owner WIP that overlaps this branch. A direct merge would risk overwriting or conflating that work. The verified feature branch and this handoff are the safe durable result; `main` remains untouched at `fa4405a`.

On this machine, where `smartuni-app` occupies port `8000`, the owner can start the full tested profile with one PowerShell command:

```powershell
$env:API_PORT='8180'; docker compose -f compose.yaml --profile admin up -d
```

Then open:

- interface: `http://127.0.0.1:3000/`;
- API docs: `http://127.0.0.1:8180/docs`;
- optional admin: `http://127.0.0.1:8501/`.

Normal stop, preserving data:

```powershell
$env:API_PORT='8180'; docker compose -f compose.yaml --profile admin down
```

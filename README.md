# Investment Due Diligence Agent

Local-first Python project for the Stage 1A public company due diligence MVP.

## Runtime

- Python: `3.12`
- Package manager: `uv`
- Default dependency groups: none; select groups explicitly with `--no-default-groups`.

## Bootstrap

```powershell
uv python install 3.12 3.13
uv python pin 3.12
uv lock --python 3.12
uv sync --no-default-groups --group stage1a --group stage1a-rag-local --group dev
```

## Windows WeasyPrint Runtime

WeasyPrint needs the native Pango/GLib runtime on Windows. Use the official MSYS2 route:

```powershell
pacman -S mingw-w64-x86_64-pango
```

If MSYS2 is installed in the official default location, expose the DLL directory for checks:

```powershell
$env:WEASYPRINT_DLL_DIRECTORIES = 'C:\msys64\mingw64\bin'
```

For a user-scope MSYS2 install, use:

```powershell
$env:WEASYPRINT_DLL_DIRECTORIES = "$env:USERPROFILE\msys64\mingw64\bin"
```

Verify the runtime before the Stage 1A smoke:

```powershell
uv run --no-default-groups --group stage1a --group stage1a-rag-local python -m weasyprint --info
```

## Smoke Checks

```powershell
uv run --no-default-groups --group stage1a --group stage1a-rag-local python -c "import pydantic,httpx,langgraph,openai,pandas,duckdb,streamlit,matplotlib,plotly,weasyprint,sentence_transformers,faiss; import langgraph.checkpoint.sqlite; print('stage1a ok')"
uv run --no-default-groups --group stage1a --group stage1a-rag-local --group dev pytest tests/unit/test_config.py -v
uv run --python 3.13 --no-default-groups --group stage1a --group stage1a-rag-local python -c "import pydantic,httpx,langgraph,openai,pandas,duckdb,streamlit,matplotlib,plotly,weasyprint,sentence_transformers,faiss; print('py313 stage1a ok')"
```

## Gate B Offline Evaluation

Gate B is frozen to `public_us_frozen_v1`. The evaluator uses fixture adapters only, blanks `OPENAI_API_KEY`, disables tracing, validates fixture hashes, runs the local approval workflow, renders approved JSON/HTML/PDF artifacts, and writes `output/gate-b/public_us_frozen_v1/eval-result.json`.

```powershell
.\scripts\run_stage1a_eval.ps1
```

Equivalent CLI:

```powershell
$env:OPENAI_API_KEY = ''
$env:LANGSMITH_TRACING = 'false'
$env:DDA_LANGSMITH_TRACING = 'false'
uv run --offline --no-sync --no-default-groups --group stage1a --group stage1a-rag-local --group eval-ragas --group dev investment-dd run-eval --dataset public_us_frozen_v1
```

## Browser Demo

Run Streamlit with fixture mode and use the Public Company page:

```powershell
uv run --no-default-groups --group stage1a --group stage1a-rag-local streamlit run src/due_diligence_agent/presentation/streamlit/app.py
```

Create the `AAPL` case, approve the fixture workflow, then download the approved report JSON, HTML, and PDF from the report section.

## Founder API

The Founder API is the local browser/API surface for delivery profile B. It binds to `127.0.0.1` by default and does not expose itself on the network unless `-AllInterfaces` is passed explicitly.

Install the API/runtime groups:

```powershell
uv sync --no-default-groups --group stage1a --group founder-api --group dev
```

Run locally:

```powershell
.\scripts\run_founder_api.ps1 -Port 8000
```

Equivalent CLI:

```powershell
uv run --offline --no-sync --no-default-groups --group stage1a --group founder-api --group dev investment-dd-api --port 8000
```

Local URLs:

- Founder API: `http://127.0.0.1:8000`
- API docs: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/health/live`
- Capabilities contract: `http://127.0.0.1:8000/api/v1/product/capabilities`

Surface split:

- Founder Workspace: separate Next.js product UI for universal upload, the same-case primary/deep analysis dossier, and founder-safe public comparables.
- Founder API: versioned FastAPI contract consumed by the Founder Workspace.
- Admin Console: separate Streamlit surface for operator tracing, evaluations, privacy, source health, and cost/latency controls.
- Startup analysis capabilities remain explicitly `planned` until safe ingest and the startup workflow are implemented; the UI does not manufacture results.

Expose on all interfaces only for trusted local demos:

```powershell
.\scripts\run_founder_api.ps1 -Port 8000 -AllInterfaces
```

## Founder Workspace

Install the browser dependencies once:

```powershell
npm --prefix frontend/founder ci
```

Start the full local workspace with one shared data directory for the Founder API, Founder Workspace, and Streamlit Admin Console:

```powershell
.\scripts\start_founder_workspace.ps1 -DataDir .tmp-founder-demo
```

For a local, no-cost browser rehearsal over the documents you actually upload, select the explicit deterministic mode. The default remains `live`:

```powershell
.\scripts\start_founder_workspace.ps1 -DataDir .tmp-founder-demo -CaseMode deterministic_offline
```

Dry-run the launch contract without starting servers:

```powershell
.\scripts\start_founder_workspace.ps1 -DataDir .tmp-founder-demo -ValidateOnly
```

Run the product UI on localhost while the Founder API is running:

```powershell
npm --prefix frontend/founder run dev -- --hostname 127.0.0.1 --port 3000
```

Product URLs:

- Founder Workspace: `http://127.0.0.1:3000/`
- Founder-safe Public Comparables: `http://127.0.0.1:3000/comparables`
- Admin bridge: `http://127.0.0.1:3000/admin`
- Streamlit Admin Console: `http://127.0.0.1:8501/`

## Docker Compose

Docker Compose упаковывает весь локальный продукт: Founder Workspace, Founder API и опциональную Streamlit Admin Console. Текущий Docker-контракт по умолчанию запускает live workflow: онлайн-ресерч работает после добавления ваших OpenAI-ключей в приватный `.env`, а санитизированный LangSmith exporter включён флагом `DDA_LANGSMITH_TRACING=true` и отправляет трассы только при наличии `LANGSMITH_API_KEY`. Файл-пример окружения безопасен для GitHub: поля ключей оставлены пустыми.

Подробная русская инструкция для проверяющего: [GITHUB_REVIEWER_GUIDE_RU.md](GITHUB_REVIEWER_GUIDE_RU.md).

Создайте локальный `.env`:

```powershell
Copy-Item .env.docker.example .env
```

Запустите интерфейс и API:

```powershell
docker compose up --build
```

Откройте:

- Founder Workspace: `http://127.0.0.1:3000/`
- API docs: `http://127.0.0.1:8000/docs`

Если порт `8000` уже занят другим локальным проектом, задайте свободный host-порт без изменения контейнера:

```powershell
$env:API_PORT='8180'; docker compose up --build
```

В этом случае документация API будет доступна по адресу `http://127.0.0.1:8180/docs`. Внутри Compose интерфейс по-прежнему обращается к API через сервис `api:8000`.

Запустите тот же продукт вместе с опциональной админкой:

```powershell
docker compose --profile admin up --build
```

Адрес админки:

- Streamlit Admin Console: `http://127.0.0.1:8501/`

Обычная остановка сохраняет именованный Docker volume с данными кейсов:

```powershell
docker compose down
```

Именованный volume нужен намеренно: API и Admin используют общий путь `/app/data`, поэтому локальное состояние кейса переживает перезапуск контейнеров. Live-режим уже выбран значением `FOUNDER_CASE_FIXTURE_MODE=live`; для no-cost проверки без интернета задайте в приватном `.env` `FOUNDER_CASE_FIXTURE_MODE=deterministic_offline`. Для реального онлайн-ресерча добавьте `OPENAI_API_KEY`, `OPENAI_STARTUP_API_KEY` и при необходимости `LANGSMITH_API_KEY` в ваш приватный `.env`; `.env.docker.example` должен оставаться пустым и безопасным для коммита. Санитизированный LangSmith exporter включён флагом `DDA_LANGSMITH_TRACING=true`, но без `LANGSMITH_API_KEY` ничего не отправляет во внешний LangSmith.

`docker compose down -v` специально удаляет именованный volume и стирает локальные данные кейсов. Не используйте эту команду для обычной остановки.

Docker-образы и build cache не кладутся в GitHub. В репозиторий попадают только исходники, Dockerfile, Compose-конфигурация, тесты и документация.

## Delivery profile B and later C

Profile B is the current sellable single-operator product foundation. Profile C adds authenticated users, workspaces, tenant policy, production persistence, durable jobs, and operational guarantees behind the existing application ports and `/api/v1` contracts.

Analytics depth is identical in B and C: universal upload, primary analysis, deep analysis, evidence rules, metric definitions, risk logic, Reflexion, and report semantics do not change. See the complete [B-to-C architecture boundary and migration checklist](docs/architecture/2026-08-12-sales-ready-hybrid-boundaries.md).

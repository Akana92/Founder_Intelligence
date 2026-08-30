# План завершения UX ИИ-советника для основателя

> **Для агентных исполнителей:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Шаги используют синтаксис чекбоксов (`- [ ]`) для отслеживания прогресса.

**Цель:** Превратить существующую систему инвестиционного due diligence в русскоязычного ИИ-советника для основателя, рассчитанного только на компьютер. Система должна сразу давать полезный анализ, задавать по одному самому важному уточнению за раз и предлагать конкретные улучшения стартапа.

**Архитектура:** Оставить проверенный backend, доказательства, контрольные точки, отчеты, рабочий процесс LangGraph, подтверждение LangSmith и smoke-проверку OpenAI как фундамент. Над существующими каноническими данными добавить слой представления для основателя и контракты цикла советника, чтобы сырые технические состояния не попадали в пользовательский интерфейс, а раздел Admin и проверка оставались строгими. В режиме `live` внешняя LLM `gpt-5.6-luna` работает только через существующий Privacy/LLM Gateway после Gate 2; в режиме `deterministic_offline` система использует детерминированные адаптеры и не вызывает OpenAI.

**Технологический стек:** Python 3.12/3.13, Pydantic, pytest, Ruff, strict mypy, LangGraph, FastAPI, Next.js, frontend основателя, TypeScript-тесты, Playwright/browser smoke, побочные доказательства LangSmith, ограниченная smoke-проверка конкурентов через OpenAI.

## Глобальные ограничения

- Только компьютерная версия. Не проектировать, не реализовывать и не проверять новый мобильный интерфейс для этого редизайна.
- Русский язык является языком по умолчанию для рабочего пространства основателя, отчетов, которые видит основатель, вопросов, блокеров и ИИ-рекомендаций.
- Никогда не показывать сырые `MISSING`, внутренние хэши источников, сырые блоки документов, локальные пути, промпты, секреты или внутренности трассировки в интерфейсе основателя.
- Технические доказательства остаются доступными через Admin, отчеты и артефакты проверки без ослабления защиты приватности.
- Queue 1-4 не переписываются.
- Старые доказательства Queue 5 сохраняются, но не закрывают новую приемку удобного интерфейса для основателя.
- Автономные контрольные точки остаются детерминированными и не зависят от сети.
- Доказательства трассировки LangSmith и smoke-проверка конкурентов через OpenAI остаются отдельными побочными доказательствами; они не меняют каноническую семантику Gate D/E.
- Публичный поиск требует явного разрешения пользователя и должен маркироваться как исследование по публичным источникам.
- Публичные сведения исследует отдельный Research Agent: Luna формирует безопасный план и синтез, а ограниченный поисковый инструмент получает реальные источники. Ответ модели без источника не становится подтвержденным фактом.
- Внутренние финансовые и клиентские данные нужно запрашивать у пользователя или брать из загруженных файлов; не подразумевать, что их всегда можно найти в интернете.
- Канонические метрики, вычисления, решения Gates и происхождение отчета не определяются LLM.
- Текущая модель OpenAI для startup-пути — только `gpt-5.6-luna`, заданная через `OPENAI_STARTUP_MODEL`; смена модели требует отдельного ценового профиля, тестов и fallback-контракта, а не простой замены строки в `.env`.
- Принятые ИИ-улучшения создают новую версию проекта; отклоненные улучшения сохраняют предыдущую версию.
- Использовать только явный `git add -- <paths>`. Не добавлять в индекс protected WIP, runtime folders, screenshots, reports, PDFs, uploads или probe files.

---

## Карта ответственности файлов

- `PROJECT_COMPLETION_ROADMAP.md`: короткий трекер прогресса для владельца проекта.
- `MOCKUPS.md`: каноническая ссылка на визуальный источник и UX-контракт.
- `mockups/founder-intelligence-desktop/README.md`: индекс экранов и последовательность демонстрации.
- `src/due_diligence_agent/domain/startup/`: канонические сущности профиля стартапа, готовности, GTM и рынка.
- `src/due_diligence_agent/application/services/`: доменные сервисы, которые формируют профиль, метрики, готовность, рынок, GTM, отчет и представления трассировки.
- `src/due_diligence_agent/ports/startup_research.py`: независимый контракт frozen/live исследования стартапа.
- `src/due_diligence_agent/adapters/openai/startup_web_research.py`: ограниченный live-адаптер публичного поиска через OpenAI с обязательными источниками.
- `src/due_diligence_agent/presentation/api/routers/startup.py`: API-поверхность основателя для кейсов, анализа, подтверждений, отчетов и будущих endpoints советника.
- `frontend/founder/lib/`: TypeScript-контракты представления и тесты отображения. Читать `frontend/founder/AGENTS.md` перед изменением этой папки.
- `frontend/founder/components/`: компоненты компьютерного интерфейса основателя. Читать `frontend/founder/AGENTS.md` перед изменением этой папки.
- `docs/demo/`: сценарий защиты и карта соответствия требованиям capstone.
- `docs/verification/`: финальные записи доказательств.

---

### Задача 0: Согласовать канонический продуктовый контракт только для компьютера

**Файлы:**
- Изменить: `PRODUCT.md`
- Изменить: `DESIGN.md`
- Проверить: `MOCKUPS.md`
- Проверить: `mockups/founder-intelligence-desktop/README.md`

**Контракт:**
- Редизайн рабочего пространства основателя и его визуальная приемка относятся только к компьютерной версии.
- Существующие исторические мобильные доказательства Queue 5 остаются неизменяемым прошлым артефактом проверки, а не требованием к переработанному продукту.
- Русский язык является языком по умолчанию для продукта и отчета, которые видит основатель.

- [ ] **Шаг 1: Зафиксировать текущее противоречие**

Выполнить:

```powershell
rg -n -i "mobile|390x844|620px|desktop" PRODUCT.md DESIGN.md MOCKUPS.md mockups/founder-intelligence-desktop/README.md
```

Ожидаемо: `PRODUCT.md` и `DESIGN.md` все еще содержат положительные требования к мобильной версии, тогда как `MOCKUPS.md` исключает мобильную версию.

- [ ] **Шаг 2: Обновить только каноническую формулировку продукта и дизайна**

Удалить положительные требования к реализации и приемке мобильной версии из `PRODUCT.md` и `DESIGN.md`. Сохранить доступность на компьютере, навигацию с клавиатуры, контрастность WCAG AA, читаемые таблицы и демонстрационную цель 1440px. Не редактировать исторические записи проверки, чтобы стереть ранее собранные мобильные доказательства.

- [ ] **Шаг 3: Проверить согласованность контракта**

Повторно выполнить поиск и просмотреть каждое совпадение. Ожидаемо: все оставшиеся упоминания мобильной версии в текущих продуктовых источниках и макетах описывают ее как исключенную; ни один текущий источник не запрашивает мобильный layout, breakpoint, smoke или mockup.

- [ ] **Шаг 4: Закоммитить только файлы контракта**

```powershell
git add -- PRODUCT.md DESIGN.md
git commit -m "docs(founder): lock desktop-only advisor scope"
```

---

### Задача 1: Зафиксировать языковой контракт для основателя

**Файлы:**
- Создать: `tests/unit/application/test_founder_advisor_presentation.py`
- Создать: `src/due_diligence_agent/application/services/founder_advisor_presentation_service.py`
- Изменить: `src/due_diligence_agent/application/services/__init__.py`

**Интерфейсы:**
- Формирует: `FounderAdvisorCard(title_ru: str, summary_ru: str, status: Literal["confirmed", "estimated", "needs_input", "contradiction"], why_it_matters_ru: str, next_unlock_ru: str | None)`.
- Формирует: `FounderAdvisorPresentationService.build(snapshot: StartupReportSnapshot) -> FounderAdvisorView`.

- [ ] **Шаг 1: Написать падающие тесты для русскоязычных карточек**

```powershell
uv run pytest tests/unit/application/test_founder_advisor_presentation.py -q
```

Ожидаемое первое падение: module `founder_advisor_presentation_service` does not exist.

- [ ] **Шаг 2: Проверить этими тестами точные правила**

```python
def test_missing_values_become_actionable_russian_guidance() -> None:
    view = FounderAdvisorPresentationService().build(snapshot_with_missing_mrr())
    card = view.metric_cards["mrr"]
    assert card.status == "needs_input"
    assert "не хватает данных" not in card.summary_ru.lower()
    assert "добавьте MRR" in card.next_unlock_ru
    assert "точнее оценить выручку" in card.next_unlock_ru
    assert "MISSING" not in repr(view)

def test_confirmed_and_estimated_values_are_visually_distinct() -> None:
    view = FounderAdvisorPresentationService().build(snapshot_with_confirmed_and_estimated_metrics())
    assert view.metric_cards["gross_margin"].status == "confirmed"
    assert view.metric_cards["tam"].status == "estimated"
    assert "гипотеза" in view.metric_cards["tam"].summary_ru.lower()
```

- [ ] **Шаг 3: Реализовать минимальное отображение**

Преобразовать существующие канонические поля в русские заголовки, краткие выводы и статусы. Использовать только детерминированные шаблоны. Не вызывать OpenAI в этой задаче.

- [ ] **Шаг 4: Проверить**

```powershell
uv run pytest tests/unit/application/test_founder_advisor_presentation.py -q
uv run ruff check src/due_diligence_agent/application/services/founder_advisor_presentation_service.py tests/unit/application/test_founder_advisor_presentation.py
uv run mypy src/due_diligence_agent/application/services/founder_advisor_presentation_service.py
```

- [ ] **Шаг 5: Commit**

```powershell
git add -- src/due_diligence_agent/application/services/founder_advisor_presentation_service.py src/due_diligence_agent/application/services/__init__.py tests/unit/application/test_founder_advisor_presentation.py
git commit -m "feat(founder): add Russian advisor presentation contract"
```

---

### Задача 2: Добавить контракт постепенных уточнений

**Файлы:**
- Создать: `src/due_diligence_agent/domain/startup/advisor.py`
- Создать: `tests/unit/domain/test_startup_advisor.py`
- Создать: `src/due_diligence_agent/application/services/startup_advisor_service.py`
- Создать: `tests/unit/application/test_startup_advisor_service.py`

**Интерфейсы:**
- Формирует: `AdvisorQuestion(question_id, field_key, question_ru, reason_ru, unlocks_ru, answer_modes)`.
- Формирует: `AdvisorAnswer(answer_type: Literal["manual", "file", "public_research", "skip"], value: str | None, consent_public_research: bool = False)`.
- Формирует: `StartupAdvisorService.next_question(case_id: UUID) -> AdvisorQuestion | None`.
- Формирует: `StartupAdvisorService.apply_answer(case_id: UUID, question_id: str, answer: AdvisorAnswer) -> AdvisorDelta`.

- [ ] **Шаг 1: Написать падающие доменные тесты**

Потребовать один лучший вопрос, отсутствие длинной анкеты, детерминированный приоритет, согласие на публичный поиск и поведение пропуска, которое снижает доверие, но не блокирует анализ.

- [ ] **Шаг 2: Выполнить RED**

```powershell
uv run pytest tests/unit/domain/test_startup_advisor.py tests/unit/application/test_startup_advisor_service.py -q
```

- [ ] **Шаг 3: Реализовать детерминированный приоритет**

Порядок приоритета для первого прохода:

1. выручка или модель ценообразования, которая открывает MRR/ARR/gross margin;
2. клиентский сегмент/ICP, который открывает позиционирование и конкурентов;
3. текущая traction, которая открывает оценку готовности;
4. burn/cash, который открывает runway;
5. GTM-канал, который открывает план действий.

- [ ] **Шаг 4: Проверить**

```powershell
uv run pytest tests/unit/domain/test_startup_advisor.py tests/unit/application/test_startup_advisor_service.py -q
uv run ruff check src/due_diligence_agent/domain/startup/advisor.py src/due_diligence_agent/application/services/startup_advisor_service.py tests/unit/domain/test_startup_advisor.py tests/unit/application/test_startup_advisor_service.py
uv run mypy src/due_diligence_agent/domain/startup/advisor.py src/due_diligence_agent/application/services/startup_advisor_service.py
```

- [ ] **Шаг 5: Commit**

```powershell
git add -- src/due_diligence_agent/domain/startup/advisor.py src/due_diligence_agent/application/services/startup_advisor_service.py tests/unit/domain/test_startup_advisor.py tests/unit/application/test_startup_advisor_service.py
git commit -m "feat(founder): add progressive advisor question loop"
```

---

### Задача 3: Подключить настоящий публичный Research Agent

**Файлы:**
- Изменить: `src/due_diligence_agent/domain/startup/market.py`
- Изменить: `src/due_diligence_agent/application/services/startup_market_research_service.py`
- Создать: `src/due_diligence_agent/application/services/startup_advisor_research_service.py`
- Создать: `src/due_diligence_agent/adapters/openai/startup_web_research.py`
- Изменить: `src/due_diligence_agent/workflows/startup/ports.py`
- Изменить одним интегратором: `src/due_diligence_agent/bootstrap/container.py`
- Создать: `tests/unit/application/test_startup_advisor_research_service.py`
- Изменить: `tests/integration/retrieval/test_startup_market_research.py`
- Изменить: `tests/privacy/test_ai_egress.py`

**Интерфейсы:**
- Использует существующий `StartupResearchPort.collect(plan: StartupResearchPlan) -> StartupMarketResearchSnapshot`.
- Формирует: `StartupAdvisorResearchService.research(case_id: UUID, question: AdvisorQuestion, answer: AdvisorAnswer) -> AdvisorResearchDelta`.
- Формирует: `AdvisorResearchDelta(status: Literal["completed", "partial", "deferred", "blocked"], summary_ru: str, source_ids: tuple[UUID, ...], fallback_used: bool, fail_reason_ru: str | None)`.
- `StartupMarketResearchService.build_research_plan(..., source_mode=StartupResearchSourceMode.LIVE)` создает не более трех очищенных запросов для одного вопроса.

- [ ] **Шаг 1: Написать падающие тесты согласия, границ и fallback**

Проверить точные правила:

```python
def test_public_research_requires_explicit_consent_before_provider_call() -> None:
    service, client = build_research_service()
    answer = AdvisorAnswer(answer_type="public_research", consent_public_research=False)
    delta = service.research(CASE_ID, PUBLIC_ICP_QUESTION, answer)
    assert delta.status == "blocked"
    assert client.calls == []

def test_internal_metric_question_never_routes_to_web_search() -> None:
    service, client = build_research_service()
    answer = AdvisorAnswer(answer_type="public_research", consent_public_research=True)
    delta = service.research(CASE_ID, PRIVATE_MRR_QUESTION, answer)
    assert delta.status == "blocked"
    assert client.calls == []

def test_live_public_research_returns_bounded_cited_sources() -> None:
    service, client = build_research_service(public_hits=PUBLIC_HITS[:5])
    delta = service.research(CASE_ID, PUBLIC_COMPETITOR_QUESTION, CONSENTED_SEARCH)
    assert delta.status == "completed"
    assert 1 <= len(delta.source_ids) <= 5
    assert len(client.calls) == 1

def test_search_outage_uses_cached_fallback_without_breaking_case() -> None:
    service, _ = build_research_service(provider_error=TimeoutError())
    delta = service.research(CASE_ID, PUBLIC_COMPETITOR_QUESTION, CONSENTED_SEARCH)
    assert delta.status == "partial"
    assert delta.fallback_used is True
```

- [ ] **Шаг 2: Выполнить RED**

```powershell
uv run pytest tests/unit/application/test_startup_advisor_research_service.py tests/integration/retrieval/test_startup_market_research.py tests/privacy/test_ai_egress.py -q
```

Ожидаемо: отсутствуют новый сервис и live-адаптер; текущий workflow отклоняет любой `source_mode`, кроме `FROZEN`.

- [ ] **Шаг 3: Реализовать минимальный ограниченный live-путь**

Research Agent должен:

1. принимать только `answer_type="public_research"` с `consent_public_research=True`;
2. отклонять вопросы о MRR, ARR, burn, cash, клиентах, договорах и других внутренних данных;
3. передавать Luna только очищенные поля продукта, ICP, географии и публично проверяемую тему;
4. выполнять максимум один provider-вызов, три запроса, пять источников и timeout 15 секунд;
5. сохранять для каждого источника URL, название, `as_of`, время получения, SHA-256, статус и уверенность;
6. маркировать результат как `live_public_research`, а вывод Luna — как `live_inference`;
7. при timeout, budget или provider outage возвращать frozen/cached результат со статусом `partial`, не прерывая кейс;
8. никогда не отправлять сырой PDF, текст документа, имя файла, локальный путь, промпт, PII или secret;
9. оставлять режим `deterministic_offline` без импорта сетевого клиента и с нулем внешних вызовов.

- [ ] **Шаг 4: Проверить focused-путь, privacy, Ruff и mypy**

```powershell
uv run pytest tests/unit/application/test_startup_advisor_research_service.py tests/integration/retrieval/test_startup_market_research.py tests/privacy/test_ai_egress.py tests/graph/test_startup_workflow.py -q
uv run ruff check src/due_diligence_agent/domain/startup/market.py src/due_diligence_agent/application/services/startup_market_research_service.py src/due_diligence_agent/application/services/startup_advisor_research_service.py src/due_diligence_agent/adapters/openai/startup_web_research.py src/due_diligence_agent/workflows/startup/ports.py tests/unit/application/test_startup_advisor_research_service.py tests/integration/retrieval/test_startup_market_research.py tests/privacy/test_ai_egress.py
uv run mypy src/due_diligence_agent/domain/startup/market.py src/due_diligence_agent/application/services/startup_market_research_service.py src/due_diligence_agent/application/services/startup_advisor_research_service.py src/due_diligence_agent/adapters/openai/startup_web_research.py src/due_diligence_agent/workflows/startup/ports.py
```

- [ ] **Шаг 5: Закоммитить только Research Agent**

```powershell
git add -- src/due_diligence_agent/domain/startup/market.py src/due_diligence_agent/application/services/startup_market_research_service.py src/due_diligence_agent/application/services/startup_advisor_research_service.py src/due_diligence_agent/adapters/openai/startup_web_research.py src/due_diligence_agent/workflows/startup/ports.py src/due_diligence_agent/bootstrap/container.py tests/unit/application/test_startup_advisor_research_service.py tests/integration/retrieval/test_startup_market_research.py tests/privacy/test_ai_egress.py
git commit -m "feat(research): add consented startup public search"
```

---

### Задача 4: Добавить ИИ-предложения улучшений с версионированием

**Файлы:**
- Изменить: `src/due_diligence_agent/domain/startup/advisor.py`
- Создать: `src/due_diligence_agent/application/services/startup_improvement_service.py`
- Создать: `tests/unit/application/test_startup_improvement_service.py`
- Изменить: `src/due_diligence_agent/application/services/startup_report_service.py`

**Интерфейсы:**
- Формирует: `StartupImprovementProposal(proposal_id, target_area, recommendation_ru, rationale_ru, expected_effect_ru, evidence_refs, confidence)`.
- Формирует: `StartupVersionDelta(previous_version, new_version, accepted_proposal_ids, rejected_proposal_ids, changed_fields)`.

- [ ] **Шаг 1: Написать падающие тесты**

Потребовать предложения для позиционирования, монетизации, метрик, GTM, снижения рисков и готовности к инвестору. Потребовать, чтобы accept/reject сохраняли происхождение данных и удерживали артефакты отчета привязанными к одной утвержденной версии.

- [ ] **Шаг 2: Выполнить RED**

```powershell
uv run pytest tests/unit/application/test_startup_improvement_service.py -q
```

- [ ] **Шаг 3: Реализовать детерминированную генерацию предложений**

Использовать существующие профиль, готовность, GTM, противоречия и краткие сводки по конкурентам. Не вызывать live OpenAI внутри детерминированных тестов. В live-режиме использовать только уже сохранённые структурированные выводы Luna и доказательства Research Agent; отдельно маркировать ИИ-вывод, публичные факты и локальные вычисления.

- [ ] **Шаг 4: Проверить**

```powershell
uv run pytest tests/unit/application/test_startup_improvement_service.py tests/unit/reporting/test_startup_report_snapshot.py -q
uv run ruff check src/due_diligence_agent/application/services/startup_improvement_service.py src/due_diligence_agent/domain/startup/advisor.py tests/unit/application/test_startup_improvement_service.py
uv run mypy src/due_diligence_agent/application/services/startup_improvement_service.py src/due_diligence_agent/domain/startup/advisor.py
```

- [ ] **Шаг 5: Commit**

```powershell
git add -- src/due_diligence_agent/domain/startup/advisor.py src/due_diligence_agent/application/services/startup_improvement_service.py src/due_diligence_agent/application/services/startup_report_service.py tests/unit/application/test_startup_improvement_service.py
git commit -m "feat(founder): add versioned startup improvement proposals"
```

---

### Задача 5: Открыть API советника

**Файлы:**
- Изменить: `src/due_diligence_agent/presentation/api/routers/startup.py`
- Изменить: `tests/api/test_startup_api.py`

**Интерфейсы:**
- Добавляет `GET /startup/cases/{case_id}/advisor/next-question`.
- Добавляет `POST /startup/cases/{case_id}/advisor/answers`.
- Добавляет `GET /startup/cases/{case_id}/advisor/improvements`.
- Добавляет `POST /startup/cases/{case_id}/advisor/improvements/{proposal_id}/decision`.

- [ ] **Шаг 1: Написать падающие API-тесты**

Потребовать происхождение в рамках того же кейса, русский текст, согласие на публичный поиск, отсутствие сырых `MISSING` и отсутствие утечки внутренних хэшей.

- [ ] **Шаг 2: Выполнить RED**

```powershell
uv run pytest tests/api/test_startup_api.py -q
```

- [ ] **Шаг 3: Реализовать маршруты**

Использовать существующие шаблоны зависимостей и контейнера. Возвращать только стабильные DTO; не раскрывать внутренности домена.

- [ ] **Шаг 4: Проверить**

```powershell
uv run pytest tests/api/test_startup_api.py tests/privacy/test_ai_egress.py -q
uv run ruff check src/due_diligence_agent/presentation/api/routers/startup.py tests/api/test_startup_api.py
uv run mypy src/due_diligence_agent/presentation/api/routers/startup.py
```

- [ ] **Шаг 5: Commit**

```powershell
git add -- src/due_diligence_agent/presentation/api/routers/startup.py tests/api/test_startup_api.py
git commit -m "feat(api): expose founder advisor loop"
```

---

### Задача 6: Пересобрать компьютерный Founder UI по утвержденным макетам

**Файлы:**
- Сначала прочитать: `frontend/founder/AGENTS.md`
- Изменить/создать в: `frontend/founder/lib/`
- Изменить/создать в: `frontend/founder/components/`
- Изменить: `frontend/founder/app/page.tsx`
- Изменить: `frontend/founder/app/admin/page.tsx` только если нужно согласовать текст Admin

**Интерфейсы:**
- Формирует экраны только для компьютера, соответствующие `mockups/founder-intelligence-desktop/01-start-dashboard.png` through `14-ai-advisor-improved-plan.png`.
- Держит доказательства Admin отдельно от анализа для основателя.

- [ ] **Шаг 1: Прочитать инструкции frontend**

```powershell
Get-Content -Raw frontend/founder/AGENTS.md
```

Перед редактированием проверить `git status --short` и diff каждого пересекающегося frontend-файла. Существующий незавершённый код владельца защищён: его нужно осознанно интегрировать, а не удалять, перезаписывать, откатывать или случайно добавлять в индекс. Общие graph/ports/container/report изменяет только один интегратор.

- [ ] **Шаг 2: Написать падающие frontend-тесты**

Потребовать русские labels, отсутствие сырых `MISSING`, отсутствие технических таблиц хэшей в представлении основателя, один следующий вопрос, четыре режима ответа, обновленное состояние дельты, принятую версию улучшения и порядок навигации на компьютере.

- [ ] **Шаг 3: Выполнить RED**

```powershell
cd frontend/founder
npm test
```

- [ ] **Шаг 4: Реализовать UI маленькими частями**

Порядок частей:

1. оболочка/навигация и стартовая панель;
2. обзор анализа/готовности;
3. страницы метрик и рынка;
4. состояния вопроса/ответа/дельты/улучшенного плана советника;
5. центр отчетов и согласование Admin.

- [ ] **Шаг 5: Проверить frontend**

```powershell
cd frontend/founder
npm test
npm run typecheck
npm run lint
npm run build
```

- [ ] **Шаг 6: Commit frontend slice**

Использовать явный `git add --` только для измененных исходников и тестов frontend. Не добавлять в индекс `.next`, screenshots, runtime files или protected WIP.

---

### Задача 7: Согласовать текст JSON/HTML/PDF-отчета

**Файлы:**
- Изменить: `src/due_diligence_agent/adapters/reports/templates/startup_report.html.j2`
- Изменить: `src/due_diligence_agent/application/services/startup_report_service.py`
- Изменить: `tests/unit/reporting/test_startup_report_snapshot.py`
- Изменить: `tests/e2e/test_startup_report.py`

**Интерфейсы:**
- Отчет для основателя использует тот же утвержденный кейс/версию, что и UI.
- Отчет показывает полезные русскоязычные сводки, блокеры, следующие данные для ввода и ИИ-предложения.
- Приложение источников остается техническим и безопасным с точки зрения приватности.

- [ ] **Шаг 1: Написать падающие тесты отчетов**

Отклонять сырые `MISSING`, сырые идентификаторы блоков документов, огромные таблицы хэшей в основных разделах отчета и diligence questions только на английском.

- [ ] **Шаг 2: Выполнить RED**

```powershell
uv run pytest tests/unit/reporting/test_startup_report_snapshot.py tests/e2e/test_startup_report.py -q
```

- [ ] **Шаг 3: Реализовать отображение текста отчета**

Использовать outputs `FounderAdvisorPresentationService` для основных разделов отчета. Приложение источников оставить ограниченным и техническим.

- [ ] **Шаг 4: Проверить**

```powershell
uv run pytest tests/unit/reporting/test_startup_report_snapshot.py tests/e2e/test_startup_report.py -q
uv run ruff check src/due_diligence_agent/adapters/reports/templates/startup_report.html.j2 src/due_diligence_agent/application/services/startup_report_service.py tests/unit/reporting/test_startup_report_snapshot.py tests/e2e/test_startup_report.py
uv run mypy src/due_diligence_agent/application/services/startup_report_service.py
```

- [ ] **Шаг 5: Commit**

```powershell
git add -- src/due_diligence_agent/adapters/reports/templates/startup_report.html.j2 src/due_diligence_agent/application/services/startup_report_service.py tests/unit/reporting/test_startup_report_snapshot.py tests/e2e/test_startup_report.py
git commit -m "feat(report): align startup report with founder advisor"
```

---

### Задача 8: Повторно проверить границу защиты проекта

**Файлы:**
- Изменить: `docs/demo/2026-08-16-sellable-demo-script.md`
- Изменить: `docs/demo/2026-08-16-capstone-requirement-evidence-map.md`
- Создать/изменить: `docs/verification/2026-08-16-founder-ai-advisor-ux-verification.md`

**Интерфейсы:**
- Формирует финальную запись доказательств для новой приемки владельцем проекта, отдельно от старых доказательств заморозки Queue 5.

- [ ] **Шаг 1: Выполнить backend-проверку**

```powershell
uv run --offline --no-sync --no-default-groups --group stage1b --group founder-api --group dev pytest -q
uv run --offline --no-sync --no-default-groups --group stage1b --group founder-api --group dev ruff check
uv run --offline --no-sync --no-default-groups --group stage1b --group founder-api --group dev mypy
```

- [ ] **Шаг 2: Выполнить frontend-проверку**

```powershell
cd frontend/founder
npm test
npm run typecheck
npm run lint
npm run build
```

- [ ] **Шаг 3: Выполнить настоящую browser smoke-проверку на компьютере**

Использовать существующую локальную smoke-проверку рабочего пространства стартапа, но требовать только путь основателя на компьютере. Smoke-проверка должна доказать загрузку, анализ, вопрос советника, ответ или пропуск, обновленный анализ, принятое улучшение, происхождение отчета и трассировку Admin.

- [ ] **Шаг 4: Выполнить проверки приватности и доказательств**

Просканировать отрендеренные доказательства UI/отчета на сырые `MISSING`, внутренние хэши в разделах для основателя, локальные пути, промпты, секреты, сырой текст PDF и неподтвержденные формулировки о живых данных.

- [ ] **Шаг 5: Выполнить живое побочное подтверждение только после offline GREEN**

Выполнить существующую очищенную smoke-проверку LangSmith. После отдельного разрешения владельца выполнить один ограниченный live-smoke Research Agent только для синтетического публичного вопроса. Выполнить ограниченную smoke-проверку конкурентов через OpenAI только если `OPENAI_API_KEY` присутствует. Зафиксировать статусы offline-пакета, Research Agent, LangSmith и OpenAI раздельно; ни одна live-проверка не меняет каноническую семантику Gate D/E.

- [ ] **Шаг 6: Обновить demo docs и verification**

Сценарий демонстрации должен показывать:

1. загрузку проекта;
2. мгновенный анализ на русском языке;
3. одно лучшее уточнение;
4. вариант ответа/загрузки/поиска/пропуска;
5. обновленные метрики и блокеры;
6. ИИ-предложение улучшения;
7. принятую версию;
8. скачивание отчета;
9. доказательство LangGraph/LangSmith в Admin.

- [ ] **Шаг 7: Commit**

```powershell
git add -- docs/demo/2026-08-16-sellable-demo-script.md docs/demo/2026-08-16-capstone-requirement-evidence-map.md docs/verification/2026-08-16-founder-ai-advisor-ux-verification.md
git commit -m "docs(demo): verify founder advisor UX readiness"
```

---

## Самопроверка

- Покрытие спецификации: план покрывает русскоязычный интерфейс для основателя, постепенное уточнение, данные от пользователя, настоящий публичный Research Agent с согласием и источниками, ИИ-предложения улучшений, отчеты, доказательства Admin, LangSmith, отдельные live-smoke Research Agent и OpenAI и проверку capstone.
- Проверка плейсхолдеров: `TBD`, `TODO` или открытые implementation placeholders не используются как содержание задач.
- Контроль объема: мобильная версия явно исключена; Queue 1-4 сохранены; старые доказательства Queue 5 не перезаписываются.
- Проверяемость: у каждой задачи есть конкретные команды проверки и критерии pass/fail.
- Условие остановки: после коммита этого документа реализация приостанавливается до следующего флажка владельца.

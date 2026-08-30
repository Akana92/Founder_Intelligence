# Founder Launch Intelligence Delivery Roadmap

> Для agentic execution после утверждения маршрута требуется отдельный подробный implementation plan на каждый независимый workstream. Рекомендуемый режим выполнения — subagent-driven development с независимым review и QA после каждой задачи.

**Goal:** преобразовать проверенный Public Company Stage 1A в продаваемый Founder-first продукт, который принимает стартап-документы без выбора отрасли, автоматически формирует первичный анализ, затем углубляет тот же кейс и демонстрирует evidence, metrics, Reflexion, tracing и PDF без переписывания готового core.

**Architecture:** текущий modular monolith, domain contracts, repositories, Evidence Ledger, Metric Engine, Privacy/LLM Gateway, LangGraph, reports и evaluation framework переиспользуются. Startup, market research, metric packs, Founder Workspace и Admin Console добавляются отдельными вертикальными срезами с жёсткими gates.

**Tech Stack:** Python 3.12/3.13, uv, Pydantic, LangGraph, OpenAI Responses API и controlled tools, deterministic Metric Engine, SQLite, DuckDB, FAISS, SEC EDGAR, optional yfinance, RSS/GDELT/web adapters, local parsers/OCR/redaction, Plotly/Matplotlib, Jinja2, WeasyPrint/ReportLab, выбранный Sales-Ready Hybrid frontend profile, существующий Streamlit shell для временного Admin Console, LangSmith, OpenTelemetry, durable local audit, pytest, Ruff, mypy, Ragas и custom evaluators.

## Global Constraints

- Главный источник продуктовых требований: [Founder Launch Intelligence — ТЗ](../specs/2026-08-11-founder-launch-intelligence-product-tz.md).
- Техническая foundation: [Investment Due Diligence Agent Design](../specs/2026-08-09-investment-due-diligence-agent-design.md).
- Готовый Public Company implementation нельзя переписывать без доказанной необходимости; изменения shared contracts должны быть backward-compatible.
- Stage 1A Gate B остаётся обязательным regression gate на протяжении всей разработки.
- Startup Graph не начинается до зелёного Gate C для ingest и privacy.
- Канонические числа считает только детерминированный Metric Engine.
- Raw startup artifacts остаются локальными; external AI работает только через Data Egress Policy и Gate 2.
- Tracing, evaluation, privacy и reproducibility не переносятся в необязательный polish.
- Founder Workspace и Admin Console являются разными пользовательскими контурами.
- Public Company становится secondary comparables mode, но его существующая функциональность и тесты сохраняются.
- Sellable demo должен работать на frozen/cached data без оплаченного API; live mode является отдельным профилем.
- Каждая стадия завершается измеримым результатом, QA evidence и stop gate.
- Владелец выбрал delivery profile B — Sales-Ready Hybrid. Это не является разрешением автоматически выполнить все стадии подряд: до implementation закрываются остальные параметры Decision Gate 0, а каждая стадия по-прежнему проходит отдельную приёмку.

---

## 1. Текущая точка старта

| Область | Текущее состояние | Решение roadmap |
|---|---|---|
| Shared domain и storage | Реализовано | Переиспользовать |
| Evidence Ledger | Реализовано для Public | Расширить Startup claims |
| Public metrics | Реализованы | Сохранить и использовать для comparables |
| LangGraph Public workflow | Реализован | Использовать как проверенный orchestration pattern |
| Reflexion и HITL | Реализованы для Public | Расширить Startup веткой |
| Privacy/LLM Gateway | Реализован | Не обходить; добавить Startup Gate 2 UX |
| Durable audit, OTel, LangSmith adapter | Реализованы | Вывести в Admin Console |
| Report JSON/HTML/PDF | Реализован для Public | Расширить Startup report contract |
| Gate B | Зелёный | Сделать постоянным regression gate |
| Public Streamlit UI | Рабочий инженерный прототип | Перестроить presentation layer без ломки services |
| Startup Data Room | Запланирован, не реализован | Реализовать через Gate C |
| Startup Profile и claims | Запланированы | Добавить после safe ingest |
| Metric packs и adaptive questions | Новый продуктовый слой | Спроектировать и реализовать отдельно |
| Founder Workspace | Новый продуктовый слой | Основной интерфейс |
| Admin Console | Частично обеспечен данными core | Отдельный интерфейс |
| Market/competitor research для startup | Частично есть public adapters | Добавить research workflow и provenance |

Прямо проверяемый baseline-снимок Stage 1A на дату roadmap — Gate B artifact `public_us_frozen_v1`, созданный 2026-08-11 для commit `f509c90b26b487238ac2f098c32711845b32e913`: `gate_b_passed=true`, fail reasons отсутствуют, JSON, HTML, PDF и audit paths сформированы. Предыдущий execution handoff сообщал 388 успешных тестов и 92 процента покрытия, но отдельный pytest/coverage artifact для этих чисел в ходе подготовки roadmap не найден. R1 обязан заново выполнить полный regression и зафиксировать test/coverage evidence перед изменениями.

## 1.1 Терминология roadmap

- **Decision Gate 0** — выбор владельца продукта, а не автоматический quality test.
- **R0–R12** — delivery stages.
- **Gate A–E** — автоматизированные evaluation gates.
- **Gate 1–4** — runtime/HITL решения внутри анализа.
- **UX Shell Review, Evidence Gate, Metric Gate и другие stage gates** — приёмка отдельной стадии; они не заменяют Gate A–E.

## 2. Принцип поставки

Roadmap разделён на три результата:

1. **Sellable Demo** — продукт можно убедительно показать основателю, инвестору или жюри.
2. **Pilot-Ready Local Product** — продукт устойчиво работает на ограниченном наборе реальных стартапов.
3. **Self-Hosted Product** — multi-user deployment, security и operations.

Sellable Demo не должен ждать всей production-инфраструктуры. При этом он не может быть набором нарисованных экранов без evidence, calculations, contradictions и tracing.

## 3. Критический путь

| Порядок | Стадия | Главный результат | Gate |
|---:|---|---|---|
| 0 | R0 — Spec Lock | Утверждённые ТЗ, roadmap и выбор маршрута | Decision Gate 0 |
| 1 | R1 — Baseline Freeze | Зафиксированная Stage 1A база и presentation contracts | Gate B regression |
| 2 | R2 — Product Experience Shell | Founder/Admin навигация и design system shell | UX Shell Review |
| 3 | R3 — Safe Startup Ingest | Универсальный Data Room, parsing и privacy | Gate C |
| 4 | R4 — Startup Intelligence Core | Startup Profile, claims и evidence matrix | Evidence Gate |
| 5 | R5 — Metrics & Guided Readiness | Metric packs, questions и readiness methodology | Metric Gate |
| 6 | R6 — Market Intelligence | Competitors, web/news, sentiment и public comps | Research Gate |
| 7 | R7 — Startup Orchestration | Plan-and-Execute, roles, Reflexion и HITL | Graph Gate |
| 8 | R8 — Founder Product & Reports | Полный пользовательский путь и PDF | Founder E2E Gate |
| 9 | R9 — Admin Console | Tracing, privacy, eval, cost и integrity | Admin Proof Gate |
| 10 | R10 — Demo Freeze | Frozen dataset, Gates D/E и investor demo package | Sellable Demo Gate |
| 11 | R11 — Pilot Hardening | Реальные грязные документы и pilot controls | Pilot Gate |
| 12 | R12 — Self-Hosted | Multi-user deployment | Production Architecture Gate |

## 4. R0 — Spec Lock и выбор маршрута

**Цель:** исключить дальнейший дрейф между Public Company analyzer, Startup analyzer и generic AI chat.

**Результаты:**

- утверждённое Founder-first ТЗ;
- утверждённый roadmap;
- зафиксированный secondary статус Public Company;
- выбранный frontend profile B — Sales-Ready Hybrid;
- зафиксированный универсальный upload flow без выбора demo vertical;
- выбранный market research profile;
- список child implementation plans.

**Stop gate:** delivery profile B и универсальный двухуровневый анализ уже выбраны, но код нового продуктового слоя не изменяется, пока владелец не закроет оставшиеся обязательные параметры Decision Gate 0.

## 5. R1 — Baseline Freeze и контракты переиспользования

**Цель:** начать новое развитие от доказанно зелёного состояния и не потерять уже сделанную работу.

**Работы:**

1. Зафиксировать текущий Stage 1A commit и Gate B artifacts.
2. Повторно выполнить минимальный Gate B regression.
3. Составить карту presentation seams, application services и shared contracts.
4. Зафиксировать, какие текущие UI helpers можно расширять, а какие presentation files разрешено заменить.
5. Зафиксировать naming migration: Public Company остаётся secondary mode, но package/domain names не переименовываются без необходимости.
6. Определить новые Startup contracts, которые не дублируют существующие Artifact, EvidenceFact, Calculation, Finding, Contradiction, Approval и ReportSnapshot.

**Acceptance:**

- Gate B зелёный;
- нет tracked изменений, не относящихся к roadmap;
- готова матрица reuse/create/extend;
- shared interfaces не изменены без tests;
- создан отдельный implementation plan следующего выбранного workstream.

**Stop gate:** любые baseline regressions исправляются до начала Startup или UI интеграции.

## 6. R2 — Product Experience Shell

**Цель:** быстро превратить инженерный прототип в понятную продуктовую оболочку, не имитируя ещё неготовые Startup-возможности.

**Работы:**

1. Ввести верхнеуровневое разделение Founder Workspace и Admin Console.
2. Сделать Startup Launch Analyzer главным пунктом продукта.
3. Переместить Public Company в Secondary / Comparable Analysis.
4. Создать дизайн-токены направления Analyst Terminal.
5. Реализовать Start, Data Room empty state, Case History и disabled/planned states.
6. Создать responsive desktop-first shell и доступную navigation.
7. Добавить единый upload entry point без выбора шаблона проекта или отрасли; внутренние demo fixtures не выводить как пользовательский каталог.

**Acceptance:**

- founder и admin навигация визуально различаются;
- главная страница объясняет продукт за один экран;
- нет default Streamlit chrome в основной demo story, если выбран Streamlit profile;
- Public Company workflow продолжает работать;
- будущие Startup разделы честно показывают состояние planned/available;
- стартовый экран не требует выбрать SaaS, marketplace, e-commerce, fintech или demo case;
- screenshot review пройден на ширине 1440;
- WCAG AA contrast и keyboard focus проверены.

**Параллельность:** visual shell может разрабатываться параллельно с R3 после фиксации application interfaces, но не должен придумывать несуществующие data contracts.

## 7. R3 — Safe Startup Ingest

**Цель:** безопасно принять mixed-format startup data room и получить локальные нормализованные artifacts.

**Работы:**

1. Проверить Stage 1B dependency groups и locked runtime.
2. Реализовать content sniffing, quotas, safe paths, archive inventory и quarantine.
3. Добавить PDF, DOCX, XLSX, CSV и image adapters.
4. Добавить cell/page locators и lineage.
5. Добавить local OCR profile после binary smoke.
6. Добавить sensitivity classification, deterministic redaction и optional Presidio adapter.
7. Ввести no-network parser guard.
8. Реализовать Gate 2 disclosure preview и default-deny behavior.

**Acceptance — Gate C:**

- unsafe archive и unsupported MIME блокируются или изолируются;
- повреждённый файл не уничтожает обработку остальных;
- no-network parsing доказан тестом;
- low-confidence OCR не становится verified evidence;
- denied Gate 2 вызывает ноль external calls;
- privacy leak count равен нулю;
- Gate B regression остаётся зелёным.

**Stop gate:** Startup AI graph не начинается до Gate C.

## 8. R4 — Startup Intelligence Core

**Цель:** превратить parsed data room в структурированный профиль, claims, evidence и gaps.

**Работы:**

1. Определить Startup Profile и business-model hypothesis.
2. Извлечь problem, solution, ICP, stage, geography, pricing, traction и assumptions.
3. Реализовать claim extraction со structured outputs.
4. Построить claim–evidence matrix.
5. Реализовать statuses verified, partially verified, contradicted, unsupported и insufficient data.
6. Добавить source priority и counter-evidence links.
7. Реализовать dependency invalidation после изменения artifact или founder correction.
8. Создать UI-friendly query services для Startup Profile и Evidence screens.

**Acceptance — Evidence Gate:**

- все critical claims имеют locator, calculation, contradiction или insufficient data;
- inference не отображается как source fact;
- исправление business model пересчитывает зависимые результаты;
- planted claim conflicts сохраняются как first-class contradictions;
- raw document text не попадает в graph state и traces;
- Public regression остаётся зелёным.

## 9. R5 — Metric Packs, Adaptive Questions и Readiness

**Цель:** дать пользователю неизвестную ему заранее методологию измерения и следующий шаг.

**Работы:**

1. Зафиксировать базовый metric registry.
2. Добавить универсальные правила и packs для SaaS, marketplace, e-commerce, fintech и других поддерживаемых моделей без ручного выбора пользователем.
3. Реализовать selection policy по business model, stage и available evidence.
4. Добавить deterministic formulas и golden calculations.
5. Реализовать missing-input analysis.
6. Реализовать Adaptive Question Engine с top-3 priority.
7. Определить versioned Launch Readiness methodology.
8. Разделить score, confidence и evidence coverage.
9. Связать risk → missing evidence → question → action → recalculation.

**Acceptance — Metric Gate:**

- на frozen cases выбран полный обязательный metric pack;
- business model и metric pack определяются автоматически; неоднозначность не блокирует первичный анализ;
- missing inputs не создают invented values;
- каждая метрика показывает formula, inputs, period и warnings;
- каждый critical missing input имеет вопрос или data-collection action;
- одинаковый snapshot даёт одинаковый readiness result;
- benchmarks без датированного сопоставимого источника не отображаются как норма.

## 10. R6 — Market, Competitor, News, Sentiment и Public Comps

**Цель:** расширить внутренние документы внешними датированными сигналами и показать глубину рынка.

**Работы:**

1. Определить research plan и разрешённые source classes.
2. Реализовать direct, indirect, substitute, do-nothing и potential entrant classification.
3. Добавить public company comparable selection.
4. Переиспользовать SEC, market и news adapters.
5. Добавить guarded web/RSS/GDELT discovery и cache.
6. Реализовать news polarity как secondary signal.
7. Добавить TAM/SAM/SOM methodology с assumptions и citations.
8. Добавить source freshness, rights flags, as-of и partial coverage.

**Acceptance — Research Gate:**

- каждый market, competitor и sentiment claim имеет source/as-of либо явную inference label;
- yfinance не является source of record;
- source outage создаёт partial section, а не выдуманный результат;
- cached/frozen demo воспроизводим без сети;
- live mode визуально отличается от fixture/cached mode;
- social coverage не заявляется без работающего официального connector/API.

## 11. R7 — Startup Plan-and-Execute, роли, Reflexion и HITL

**Цель:** объединить R3–R6 в resumable управляемый workflow.

**Работы:**

1. Создать типизированный Startup Analysis Plan.
2. Реализовать nodes Document Intelligence, Profile, Product Validation, Market, Financial, GTM, Risk, Critic и Arbiter.
3. Параллелить только независимые bounded tasks.
4. Добавить budgets, retries, fallback и stop conditions.
5. Реализовать bounded Reflexion, максимум две итерации.
6. Реализовать Gates 1–4 и dependency invalidation.
7. Добавить checkpoints, restart и idempotency.
8. Подключить durable audit и sanitized tracing для каждого node.

**Acceptance — Graph Gate:**

- happy path, partial path, retry и restart проходят;
- Gate 2 denial делает ноль external calls;
- Gate 3 pause/resume сохраняет conflict history;
- Gate 4 binding защищает final snapshot;
- Reflexion не превышает две итерации;
- каждый завершённый node имеет local audit event;
- graph state содержит references, а не raw documents;
- budget exhaustion завершает workflow контролируемо.

**Статус 2026-08-15:** R7/Queue 3 закрыта для frozen/offline scope. Critic/Arbiter и двухраундовая restart-safe Reflexion закрыты в `9fb987d`; controlled budget exhaustion — в `a039e4d`; Document Intelligence/Product Validation backend role surfaces — в `71d95b6`; deterministic GTM domain/service — в `0b315a2`; bounded graph integration, audit/trace, restart/idempotency и Gate 3 rebuild — в `43052ba`. Финальная API/query/report-lineage freeze закрыта в `54230a8`, strict Founder DTO/same-origin route — в `dbf8a98`, настоящий offline browser/API flow — в `4f72d0b`. Canonical graph store остаётся владельцем полного GTM artifact, coordinator runtime хранит только reference tuple, а `/gtm` fail-closed сверяет authoritative profile/revision/hash. См. [budget verification](../../verification/2026-08-14-queue3-budget-exhaustion-verification.md), [role-surface verification](../../verification/2026-08-15-queue3-document-product-roles-verification.md) и [GTM/API freeze verification](../../verification/2026-08-15-queue3-gtm-api-freeze-verification.md). R8/Queue 4 разблокирована и владеет полноценной Founder UI/report projection новых role outputs, Action Plan и charts.

## 12. R8 — Founder Workspace и Startup Report

**Цель:** собрать полный продаваемый пользовательский путь поверх готовых services.

**Работы:**

1. Подключить реальный Data Room inventory.
2. Подключить автоматический progress первичного анализа.
3. Разделить результаты на первичный snapshot и глубинный анализ того же кейса.
4. Реализовать Startup Profile, Readiness, Market, Product Validation, Metrics, Risks, Evidence, Questions и Action Plan screens.
5. Добавить draft/final report preview.
6. Расширить Report JSON startup sections.
7. Добавить Plotly charts и Matplotlib static fallback.
8. Добавить HTML/PDF rendering и ReportLab fallback.
9. Добавить case history и report versions.
10. Провести browser smoke и screenshot critique.

**Acceptance — Founder E2E Gate:**

- frozen startup case проходит upload → primary analysis → deep analysis → question → report без промпта и выбора отрасли;
- founder понимает missing, partial, contradiction и inference states;
- top strengths, blockers и actions связаны с evidence;
- metric education понятна нефинансовому пользователю;
- draft/final различаются;
- approved JSON, HTML и PDF доступны для скачивания;
- browser UI не раскрывает internal stack traces;
- design review подтверждает Analyst Terminal direction.

## 13. R9 — Admin Console

**Цель:** доказать управляемость, безопасность и воспроизводимость системы.

**Работы:**

1. System Overview.
2. Agent Graph.
3. Trace Explorer.
4. Evaluation Gates.
5. Privacy & Egress.
6. Sources & Cache.
7. Cost, Tokens & Latency.
8. Report Integrity.
9. Admin-only failure и retry details.

**Acceptance — Admin Proof Gate:**

- один run связывается через case, checkpoint, audit, OTel, optional LangSmith и report snapshot;
- exporter outage показан, но local audit остаётся доступным;
- privacy view не содержит raw startup content;
- Gate B–E artifacts доступны для инспекции;
- cost/budget и slow nodes видны;
- investor или reviewer может понять, что workflow контролируем и проверяем.

## 14. R10 — Evaluation, Demo Freeze и пакет для показа

**Цель:** зафиксировать воспроизводимый продуктовый сценарий и доказательства качества.

**Работы:**

1. Подготовить startup_synthetic_demo_v1 с намеренными gaps и contradictions.
2. Добавить frozen cases разных бизнес-моделей для проверки автоматической классификации и metric pack coverage.
3. Добавить UI no-prompt journey test.
4. Выполнить Gate D Startup evaluation.
5. Выполнить Gate E combined regression.
6. Выполнить privacy, report, checkpoint и exporter-outage tests.
7. Зафиксировать reference machine и latency.
8. Подготовить 7–10 минутный demo script.
9. Подготовить screenshots, sample PDF и one-page product explanation.
10. Провести финальный screenshot critique и content proofread.

**Acceptance — Sellable Demo Gate:**

- все критерии раздела 34 ТЗ выполнены;
- Gate B, C, D и E зелёные;
- full Ruff, mypy и pytest зелёные;
- frozen demo работает без ключа и сети;
- live mode, если включён, имеет отдельный smoke и маркировку;
- sample PDF не содержит недоказанных critical claims;
- Founder Workspace и Admin Console готовы к последовательному показу;
- известные ограничения перечислены в продукте и demo script.

## 15. R11 — Pilot Hardening

**Цель:** перейти от идеального frozen demo к ограниченному реальному использованию.

**Работы:**

- расширить parser/OCR fixtures;
- добавить реальные грязные документы с разрешением;
- улучшить business-model ambiguity handling;
- калибровать readiness methodology;
- расширить metric packs по запросу пилотов;
- добавить source deduplication и research caching;
- укрепить resume, retention и backup;
- добавить pilot feedback и outcome evaluation;
- определить local, single-tenant hosted или self-hosted pilot profile.

**Pilot Gate:** минимум несколько разрешённых реальных кейсов проходят с документированными gaps, нулём privacy leaks и измеримой полезностью рекомендаций. Количество кейсов и целевой success metric утверждаются отдельно до начала пилота.

## 16. R12 — Self-Hosted Product

**Цель:** подготовить multi-user deployment после доказанной ценности и hardening.

**Предварительные компоненты:**

- FastAPI;
- Next.js;
- PostgreSQL и pgvector;
- S3/MinIO;
- background workers;
- OIDC и RBAC;
- OpenTelemetry Collector;
- Grafana stack;
- tenant isolation;
- retention, backup, audit export и operational SLO.

Перед R12 требуется отдельная security/tenancy specification. Перенос локального кода один к одному без этой спецификации запрещён.

## 17. Что допускается параллелить

После R1:

- UX shell и safe ingest;
- отдельные document adapters;
- metric definitions и research adapter contract tests после фиксации schemas;
- report visual design и demo fixture design;
- Admin information architecture поверх существующего audit data.

Нельзя параллелить через незакрытую зависимость:

- Startup LLM workflow до Gate C;
- readiness scoring до versioned metric/evidence contracts;
- critical recommendations до claim–evidence matrix;
- final report до Gate 4;
- live market claims до provenance contract;
- production deployment до Pilot Gate и отдельной security spec.

## 18. Child implementation plans

После выбора Decision Gate 0 создаются отдельные планы:

1. Founder/Admin Product Shell.
2. Safe Startup Data Room.
3. Startup Profile and Claim–Evidence Core.
4. Metric Packs, Adaptive Questions and Readiness.
5. Market, Competitor, News and Sentiment Research.
6. Startup LangGraph and HITL.
7. Founder Workspace and Startup Report.
8. Admin Console and Observability UX.
9. Evaluation and Sellable Demo Freeze.

[Существующий Startup Data-Room Local MVP plan](2026-08-09-startup-data-room-local-mvp.md) используется как техническая база для пунктов 2, 3 и 6, но перед исполнением дополняется требованиями Founder-first ТЗ. Он не используется вслепую как старый product roadmap.

## 19. Delivery profiles и принятое решение

Варианты B и C реализуют одинаковую продуктовую логику: универсальную загрузку, первичный анализ и глубинный анализ. C не даёт пользователю «более глубокий» отчёт. Он добавляет более тяжёлую production-платформу вокруг той же аналитики.

| Отличие | B — Sales-Ready Hybrid | C — Full Platform First |
|---|---|---|
| Аналитические возможности | Полный первичный и глубинный анализ | Те же первичный и глубинный анализ |
| Пользовательская поверхность | Отдельный product-grade Founder frontend | Product-grade frontend в составе полной платформы |
| Backend | Переиспользуемый Python application/API core | Формализованный production API и platform services |
| Admin | Временно может переиспользовать Streamlit | Полностью интегрированная production Admin Console |
| Эксплуатация | Быстрое продаваемое демо и ограниченный pilot | Multi-user self-hosted deployment, auth, RBAC, tenancy, backup и SLO |
| Срок до первого полезного показа | Короче | Существенно дольше |

### Вариант A — Capstone Demo Fast

**Статус:** не выбран.

**Frontend:** premium Streamlit для Founder и Admin.

**Research:** frozen/cached, live optional.

**Плюсы:** максимальное переиспользование, быстрый путь к демонстрации всех capstone-технологий.

**Компромисс:** сложнее достичь ощущения полноценного коммерческого SaaS; понадобится аккуратная работа с custom styling/components.

**Когда выбирать:** если главный срок — защита capstone и ранний investor demo.

### Вариант B — Sales-Ready Hybrid

**Статус:** выбран владельцем продукта 2026-08-11.

**Frontend:** отдельный product-grade Founder frontend, Python application/API backend; Admin Console может временно переиспользовать Streamlit.

**Research:** автоматический combined profile — guarded live sources при доступности и разрешении, cached/frozen fallback для воспроизводимости; пользователь не выбирает технический режим.

**Плюсы:** наиболее сильная продающая поверхность при сохранении готового Python core.

**Компромисс:** больше integration work и отдельный frontend build.

**Когда выбирать:** если демо планируется показывать потенциальным клиентам или инвесторам как основу настоящего продукта.

**Зафиксированное решение:** вариант B является обязательным delivery profile для следующего implementation plan. Это сохраняет готовый Python core, создаёт отдельную продающую Founder-поверхность и позволяет временно переиспользовать Streamlit в Admin Console.

### Вариант C — Full Platform First

**Статус:** не выбран; может быть повторно рассмотрен после Sellable Demo Gate.

**Frontend/API:** сразу полный Next.js/FastAPI self-hosted stack.

**Плюсы:** ранняя production architecture.

**Компромисс:** высокая стоимость, более поздний первый полезный demo, риск потратить усилия на инфраструктуру до подтверждения ценности.

**Рекомендация:** не выбирать до Sellable Demo Gate.

## 20. Decision Gate 0

Состояние выбора перед началом implementation:

1. Delivery variant — выбран B, Sales-Ready Hybrid.
2. User flow — выбран универсальный upload без demo vertical; система сама определяет бизнес-модель и строит первичный и глубинный анализ.
3. Research mode — выбран combined: guarded live при доступности и разрешении, cached/frozen fallback без отдельного пользовательского переключателя.
4. Parser profile — остаётся выбрать light baseline, baseline плюс OCR или extended.
5. Язык первого интерфейса — остаётся выбрать русский, английский или bilingual.

После закрытия оставшихся пунктов создаётся только первый подробный implementation plan, выполняется его задача, запускается QA и результат показывается владельцу. Следующий workstream не начинается автоматически без закрытия его входного gate.

## 21. Definition of Done

### Sellable Demo

Единственный источник продуктовой приёмки Sellable Demo — раздел 34 Founder Launch Intelligence ТЗ. Roadmap добавляет только delivery-level доказательства:

- Gate B regression и Gate C–E зелёные;
- полный Ruff, mypy и pytest зелёные;
- frozen demo проходит без ключа и сети;
- универсальная загрузка приводит к первичному и глубинному анализу без выбора отрасли;
- visual и content reviews пройдены;
- QA artifacts, commit/build, dataset и hashes зафиксированы.

### Pilot-Ready

- реальные разрешённые кейсы обработаны;
- parser/OCR и ambiguity failures измерены;
- readiness methodology откалибрована;
- retention, backup, cost и privacy controls утверждены;
- pilot success metric достигнут или честно не достигнут.

### Production-Ready

- отдельная security/tenancy spec утверждена;
- OIDC/RBAC и tenant isolation проверены;
- backup, restore, audit retention и SLO доказаны;
- production providers и licenses утверждены;
- monitoring и incident procedures работают.

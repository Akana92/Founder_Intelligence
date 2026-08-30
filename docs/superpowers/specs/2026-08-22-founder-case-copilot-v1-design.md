# Founder Intelligence Case Copilot v1

## Архитектурная спецификация

| Поле | Значение |
|---|---|
| Проект | Capstone N3 / Founder Intelligence |
| Статус | Утверждён вариант 3; спецификация ожидает review владельца перед implementation plan |
| Дата | 2026-08-22 |
| Основная цель | Сделать AI-помощника центральным рабочим слоем кейса, а не декоративной навигацией |
| Ключевые контуры | Case Copilot, structured fact intake, safe public research, recalculation, generated assets, batch improvements |
| Визуальная граница | Сохранить текущий Founder UI, дизайн-токены и основные композиции; менять поведение и информационную архитектуру, а не арт-дирекшн |
| Архитектурная база | Существующий modular monolith, Ports and Adapters, LangGraph, Evidence Ledger и same-case revisions |

## 1. Статус и приоритет документа

Владелец продукта выбрал вариант 3: постоянный Case Copilot, единый структурированный ввод данных и реальный безопасный публичный ресерч.

Документ развивает текущую спецификацию Founder Launch Intelligence и исправляет выявленный разрыв между обещанием интерфейса и фактическим поведением. В части AI-помощника этот документ уточняет прежнее ограничение, по которому чат считался только дополнительной функцией:

- Case Copilot становится основным интерфейсом помощи и объяснения внутри готового кейса;
- структурированный workflow, Evidence Ledger, расчёты и versioned case state остаются источником истины;
- модель не записывает факт и не меняет отчёт напрямую без отдельного типизированного действия и явного подтверждения пользователя.

Приоритет источников для этой поставки:

1. Настоящая спецификация — для Case Copilot, ручного ввода, safe research, generated assets и improvement decisions.
2. `docs/superpowers/specs/2026-08-11-founder-launch-intelligence-product-tz.md` — для общего продуктового и privacy-контракта.
3. `docs/superpowers/plans/2026-08-21-founder-dynamic-analysis-fixes.md` и `docs/verification/2026-08-21-founder-dynamic-analysis-verification.md` — для уже реализованного динамического анализа и same-case recalculation.
4. Текущий код и тесты — для реально существующих интерфейсов, которые не изменены здесь явно.

## 2. Исходная проблема

Сейчас интерфейс показывает действия, которые выглядят рабочими, но фактически:

- переводят пользователя в общий экран загрузки;
- только переключают локальный UI-state;
- остаются disabled из-за отсутствующего callback;
- требуют скрытого формата ответа, который пользователь не может угадать;
- не показывают, что именно изменилось после ответа;
- не запускают отдельный market research;
- не дают ввести MRR, burn, cash, churn и другие значения вручную;
- показывают readiness как `0`, пока не существует report snapshot, даже если профиль и часть evidence уже собраны;
- предлагают принять несколько improvement proposals, хотя backend обрабатывает их по одному и меняет версию после первого решения.

Результат — пользователь не видит причинно-следственную связь:

> добавил данные или разрешил research → появились новые evidence → пересчитались метрики → изменились readiness, риски и план.

Case Copilot v1 должен сделать эту цепочку явной и проверяемой.

## 3. Целевой пользовательский результат

Основатель должен иметь возможность в любом основном разделе кейса:

1. Спросить, что система уже поняла и на каких источниках это основано.
2. Узнать, какие данные сейчас дают максимальный прирост точности.
3. Открыть готовую структурированную форму для нужного факта или метрики.
4. Понять, какие данные являются приватными и обязательно вводятся вручную или файлом.
5. Подготовить публичный research plan без внешнего запроса.
6. Явно разрешить отправку только очищенного research scope.
7. Получить источники, найденные факты и список реально обновлённых блоков.
8. Увидеть before/after для revision, evidence coverage, readiness, метрик и конфликтов.
9. Подготовить рабочий материал: сценарий интервью, pricing-тест, карту позиционирования или шаблон воронки.
10. Принять или отклонить набор улучшений одной согласованной операцией.

## 4. Не входит в Case Copilot v1

- Полный визуальный редизайн Founder Workspace.
- Новая мобильная версия.
- Multi-user аккаунты, облачная синхронизация и совместное редактирование.
- Голосовой интерфейс.
- Автоматическая отправка писем, публикация документов или изменение внешних систем.
- Streaming transport, WebSocket или новая message queue как обязательное условие v1.
- Публичный поиск приватных значений стартапа: MRR, ARR, фактическая выручка, burn, cash balance, фактические клиенты, договоры и банковские данные.
- Автоматическое превращение AI-гипотезы в подтверждённый факт.
- Подмена детерминированных расчётов арифметикой LLM.

## 5. Архитектурный принцип

Case Copilot — orchestration и explanation layer над существующим кейсом. Он не создаёт второй независимый анализ и не хранит параллельную копию продукта, метрик или отчёта.

```text
Founder UI
  ├─ Case Copilot panel
  ├─ Structured fact drawer
  ├─ Research plan / consent / job status
  └─ Existing Overview / Metrics / Market / Risks / Actions
             │
             ▼
Founder API typed commands
  ├─ Facts and conflict resolutions
  ├─ Copilot messages and suggested actions
  ├─ Research plans and jobs
  ├─ Generated assets
  └─ Batch improvement decisions
             │
             ▼
Application services
  ├─ CaseFactIntakeService
  ├─ CaseCopilotService
  ├─ SafeResearchService
  ├─ CaseAssetService
  └─ ImprovementDecisionService
             │
             ▼
Existing case state, Evidence Ledger, workflow and recalculation
  ├─ profile / claims / contradictions
  ├─ market / gtm
  ├─ metric engine
  ├─ readiness
  └─ report snapshot
```

Обязательный invariant: любой экран читает данные только из того же `case_id` и согласованной `data_revision`. Совпадение числовой revision у двух кейсов не даёт права смешивать их состояние.

## 6. Компоненты и границы ответственности

### 6.0 Каноническая mutation boundary кейса

Новый отдельный ledger для Copilot не создаётся. Каноническими остаются существующие case state, Evidence Ledger, contradiction lineage и `data_revision`.

Fact intake, подтверждённый research result, advisor answer и batch improvement используют один application-level case command coordinator, который:

- проверяет `case_id`, expected revision и idempotency;
- записывает typed evidence/decision через существующие repository patterns;
- выполняет ровно одно revision transition;
- инвалидирует stale read models;
- запускает существующий same-case recalculation boundary;
- возвращает единый founder-safe delta.

Copilot thread и generated assets хранят conversation/draft metadata, но не копируют канонические факты. Advisor manual answer становится адаптером к `CaseFactIntakeService`, а advisor public research использует общий research plan/job flow; второй набор validators и research policies запрещён.

### 6.1 CaseFactIntakeService

Назначение:

- выдаёт описание нужного ввода;
- валидирует тип, единицы, период и источник;
- сохраняет founder-confirmed evidence;
- связывает ответ с существующим gap или contradiction;
- запускает существующий same-case recalculation;
- возвращает founder-safe delta.

Сервис не:

- выбирает победителя среди противоречивых источников без подтверждения;
- удаляет прежние evidence observations;
- вызывает публичный интернет;
- рассчитывает метрики через LLM.

### 6.2 CaseCopilotService

Назначение:

- хранит один локальный thread на кейс;
- собирает bounded case context из подтверждённых фактов, gaps, открытых противоречий, research status и текущего экрана;
- отвечает понятным языком;
- предлагает типизированные действия;
- объясняет, почему действие доступно, запрещено или требует согласия.

Сервис не выполняет mutation напрямую. Его ответ может предложить действие, но сохранение факта, запуск research, генерация asset или изменение improvement version выполняются отдельным API command.

### 6.3 SafeResearchService

Назначение:

- сначала создаёт research plan без внешнего вызова;
- отделяет публично исследуемые вопросы от manual-only данных;
- показывает очищенные запросы и ожидаемые источники;
- после явного consent запускает реальный provider-backed research;
- сохраняет source-backed результаты в case evidence;
- обновляет market/GTM и запускает зависимый recalculation.

Один и тот же сервис используется из upload, Market, Advisor и Case Copilot. Отдельные конкурирующие research-пути не создаются.

### 6.4 CaseAssetService

Назначение:

- создаёт локальные рабочие черновики на основе текущей revision;
- отделяет case facts от AI-гипотез;
- сохраняет provenance: `case_id`, `data_revision`, тип asset, использованные evidence refs и время генерации;
- позволяет открыть preview, повторно сгенерировать и скачать результат.

Asset не становится evidence и не меняет readiness сам по себе.

User prompt, свободное уточнение и private case context классифицируются как `CONFIDENTIAL` по умолчанию. Если asset создаётся внешним LLM, сервис обязан использовать существующий AI gateway, bounded redacted context, minimization, audit и budget policy. Raw documents, полный chat transcript и private metric payload наружу не передаются. При запрете внешнего egress сервис создаёт детерминированный template draft либо честно возвращает blocked/deferred status.

### 6.5 ImprovementDecisionService

Назначение:

- принимает решения по всему набору proposals;
- проверяет `base_version` и полный состав decisions;
- применяет accepted proposals одной атомарной операцией;
- сохраняет rejected proposals в истории;
- создаёт ровно одну новую improvement version;
- запускает один recalculation.

## 7. Structured Fact Intake

### 7.1 Единый реестр полей

Backend хранит канонический registry для ручного ввода. UI не дублирует скрытые regex-требования.

Каждое поле описывается так:

| Атрибут | Назначение |
|---|---|
| `fact_key` | Канонический ключ: `mrr`, `burn`, `cash_balance`, `gross_margin`, `churn`, `retention`, `cac`, `customer_count`, `pricing_revenue_model`, `icp` и другие поддерживаемые поля |
| `label` | Понятное название |
| `description` | Что означает поле и зачем оно нужно |
| `value_kind` | `money`, `percent`, `count`, `duration`, `date`, `range`, `text` или `boolean` |
| `required_parts` | Какие элементы обязательны: значение, валюта, единица, период, источник, пояснение |
| `manual_only` | Нельзя получать публичным research |
| `researchable_context` | Какой внешний контекст допустимо исследовать, не подменяя private fact |
| `impacts` | Метрики, readiness factors, риски и расчёты, которые изменятся после сохранения |
| `examples` | 1–2 безопасных примера правильного заполнения |

### 7.2 API чтения требований

```http
GET /cases/{case_id}/facts/requirements
GET /cases/{case_id}/facts/requirements/{fact_key}
```

Ответ содержит:

- приоритетные gaps;
- состояние каждого поля: `missing`, `contradicted`, `provided`, `confirmed`;
- input schema;
- manual/research boundary;
- ожидаемый эффект;
- связанные contradiction/evidence refs в founder-safe форме.

### 7.3 API сохранения факта

```http
POST /cases/{case_id}/facts
```

Запрос использует discriminated value object, а не одну строку.

Пример для MRR:

```json
{
  "fact_key": "mrr",
  "value": {
    "kind": "money",
    "amount": "28.6",
    "scale": "million",
    "currency": "KZT"
  },
  "period": {
    "kind": "month",
    "start": "2026-07-01",
    "end": "2026-07-31"
  },
  "source": {
    "kind": "founder_statement",
    "declared_source": "CRM"
  },
  "note": "Рабочее значение MRR за июль",
  "resolves_contradiction_id": "contradiction-mrr-01",
  "expected_case_revision": 7,
  "idempotency_key": "client-generated-uuid"
}
```

Правила:

- money требует amount, scale и currency;
- MRR, ARR, revenue, burn и cash требуют периода или даты среза;
- manual command разрешает только `founder_statement` с заявленным источником либо ссылку на уже существующий `evidence_ref`; введённая строка `CRM` не маскируется под загруженный CRM-export;
- заявленный источник выбирается из понятных вариантов с возможностью `Другое`;
- qualitative facts используют `value.kind = text`;
- устаревшая `expected_case_revision` возвращает conflict response и свежую revision, не перетирая ввод;
- повторный `idempotency_key` не создаёт дубль;
- при разрешении противоречия прежние observations остаются в lineage, а новая запись фиксирует `resolved_by_founder`, заявленный источник и применимый период;
- `resolved_by_founder` не становится `source_fact`, пока пользователь не приложит существующий evidence ref или новый документ.

### 7.4 Хранение manual evidence

Каждый новый accepted manual command создаёт один неизменяемый локальный `Artifact` типа `founder_manual_input` в том же кейсе. Это не загруженный документ и не внешний источник.

Artifact contract:

- `source = founder_manual_input`;
- `mime_type = application/vnd.founder.fact+json`;
- payload содержит только нормализованное typed value, period, unit, declared source, note и связанные gap/contradiction ids;
- money нормализуется в canonical base amount и unit для Metric Engine, а исходный display scale сохраняется в metadata;
- `content_hash` и `source_snapshot_hash` вычисляются из одного canonical JSON payload; storage использует существующий локальный artifact store;
- `sensitivity = CONFIDENTIAL` по умолчанию;
- `SourceLocator.kind = manual_input`, `value = fact_key`, `artifact_id` указывает на этот artifact;
- `EvidenceFact.artifact_id` всегда ссылается на созданный artifact того же `case_id`;
- metadata различает `founder_statement`, `existing_evidence_ref` и `resolved_by_founder`;
- idempotent replay переиспользует тот же artifact/fact и не создаёт новый.

Если request ссылается на существующий `evidence_ref`, новый founder decision artifact всё равно фиксирует решение, а lineage metadata отдельно указывает supporting evidence. Это сохраняет историю решения и выполняет текущую referential-integrity boundary `artifact → evidence fact`.

### 7.5 Ответ и visible delta

Успешный ответ содержит:

- сохранённый founder-safe fact;
- evidence reference;
- предыдущую и новую revision;
- `recalculation_status` в существующих состояниях `started` или `deferred`;
- изменённые поля и расчёты;
- разрешённые и оставшиеся конфликты;
- before/after для evidence coverage и readiness;
- список UI sections, которые нужно refresh.

Backend переиспользует существующий same-case recalculation contract. Новый параллельный механизм revisioning не создаётся.

## 8. Case Copilot contract

### 8.1 Thread

На один `case_id` существует один локально сохраняемый thread. Сообщение хранит:

- `message_id`;
- `role`: `user`, `assistant` или `system_event`;
- `created_at`;
- `case_revision`;
- `page_context`;
- founder-safe text;
- связанные evidence refs;
- предложенные actions;
- execution result для подтверждённого действия.

Thread переживает перезапуск локального процесса. История другого кейса никогда не попадает в контекст.

User chat text классифицируется как `CONFIDENTIAL` по умолчанию. Copilot использует существующую case-level AI/privacy policy и AI gateway. Во внешний LLM допускается только bounded redacted context после minimization, audit и budget checks; raw documents, локальные пути, полный transcript и неочищенный Evidence Ledger не передаются. Если policy не разрешает внешний AI-вызов, применяется детерминированный fallback. Consent на Copilot не заменяет отдельный consent на public research, а user message никогда не превращается в public research query автоматически.

### 8.2 API

```http
GET  /cases/{case_id}/copilot/thread
POST /cases/{case_id}/copilot/messages
```

`POST /copilot/messages` принимает:

- сообщение пользователя;
- текущий раздел;
- ожидаемую revision;
- опциональный `focus_key`, если диалог открыт из metric/risk/action card.

Ответ содержит текст и массив типизированных действий:

| Action type | Назначение |
|---|---|
| `open_fact_input` | Открыть структурированную форму конкретного поля |
| `open_document_upload` | Запросить документ, когда файл надёжнее ручного значения |
| `prepare_public_research` | Создать safe research plan без внешнего вызова |
| `explain_metric` | Показать определение, формулу, обязательные входы и пример |
| `navigate` | Перейти к существующему разделу или записи |
| `prepare_asset` | Создать конкретный рабочий черновик |
| `review_improvements` | Открыть текущий набор proposals |

Каждое действие имеет:

- `status`: `available`, `requires_input`, `requires_consent`, `blocked`;
- понятный `reason`;
- typed payload;
- ожидаемый effect preview.

Заблокированное действие не изображается активной кнопкой. Причина отображается рядом.

### 8.3 Детерминированный fallback

Если LLM/provider недоступен:

- thread и история остаются доступны;
- gap ranking, metric explanation, input schema и manual/research boundary работают детерминированно;
- UI показывает `AI-ответ временно недоступен`, но предлагает реальные structured actions;
- ни один запрос не завершается ложным success.

## 9. Safe Public Research

### 9.1 Двухшаговый consent flow

Подготовка и запуск разделены.

```http
POST /cases/{case_id}/research/plans
POST /cases/{case_id}/research/jobs
GET  /cases/{case_id}/research/jobs/{job_id}
```

`POST /research/plans`:

- не вызывает внешний provider;
- принимает `expected_case_revision` и focus: `market`, `icp`, `competitors`, `alternatives`, `channels`, `public_pricing_analogs`;
- при stale revision возвращает `409` до построения plan;
- строит очищенные query previews;
- перечисляет manual-only поля, которые research не заполнит;
- возвращает `plan_id`, `plan_hash`, `case_revision`, consent text и plan со сроком жизни 30 минут.

`POST /research/jobs`:

- требует `plan_id`, `plan_hash`, `expected_case_revision`, `idempotency_key` и `consent_public_research = true`;
- проверяет, что plan принадлежит тому же case, не истёк и создан для текущей revision;
- при изменившейся revision возвращает `409 stale_research_plan`, не вызывает provider и требует новый plan;
- передаёт наружу только approved sanitized queries;
- запускает provider-backed research;
- сохраняет status и audit event.

### 9.2 Разрешённые и запрещённые темы

Разрешено искать:

- ICP и публичные характеристики сегмента;
- market/category size и growth signals;
- прямых конкурентов, косвенные заменители и публичные alternatives;
- публичные тарифы и pricing analogs конкурентов;
- доступные каналы привлечения и benchmark-сигналы;
- публичные источники, подтверждающие или опровергающие рыночную гипотезу.

Запрещено искать как факт стартапа:

- MRR, ARR и фактическую выручку;
- burn, cash balance, runway и банковские остатки;
- фактический churn, retention, CAC и margin без публичной отчётности самого кейса;
- частные договоры, списки клиентов, invoice и CRM-данные;
- персональные данные основателя или клиентов.

Copilot может исследовать публичный benchmark для приватной метрики, но benchmark сохраняется как external context, а не как значение стартапа.

### 9.3 Status model

Research job имеет состояния:

- `queued`;
- `running`;
- `completed`;
- `partial`;
- `deferred`;
- `failed`.

Job metadata сохраняется локально. Если процесс завершился во время `running`, при следующем старте job атомарно переводится в `deferred` с кодом `research_interrupted`; UI предлагает явный retry. Retry может переиспользовать plan только если TTL, `plan_hash` и `case_revision` всё ещё актуальны, иначе требуется re-plan. Незавершённый внешний вызов не считается автоматически возобновлённым или успешным.

Повтор того же `idempotency_key` возвращает исходный job. Явный retry использует новый key и поле `retry_of_job_id`; одновременно running jobs с одинаковым `plan_hash` для одного кейса запрещены.

Перед записью завершённых findings SafeResearchService повторно сверяет текущую revision с `case_revision` plan. При расхождении job становится `deferred/stale_research_plan`; source payload остаётся только в job audit, evidence и market read models не изменяются.

UI показывает:

- что именно исследуется;
- какие публичные запросы отправлены;
- сколько источников принято и отклонено;
- источник, дату доступа и краткий поддерживаемый вывод;
- какие evidence/market blocks обновлены;
- что осталось manual-only;
- почему job partial/deferred/failed.

`partial` не маскируется под `completed`.

## 10. Recalculation и readiness

### 10.1 Одна цепочка пересчёта

Любое подтверждённое изменение кейса использует одну цепочку:

```text
accepted fact or research evidence
  → new data revision
  → invalidate stale dependent snapshots
  → same-case recalculation
  → refresh profile / market / metrics / risks / actions
  → founder-safe delta
```

Copilot, Advisor, Metrics и Market не имеют собственных независимых формул readiness.

### 10.2 Readiness до и после отчёта

Главный gauge больше не принудительно равен нулю только из-за отсутствия report snapshot.

Доменный `StartupReadinessService` и его readiness dimensions сохраняются как каноническая оценка состояния. Новый presentation score агрегирует эти dimensions и совместимые fact/evidence states; он не создаёт параллельный readiness engine и не использует report-section count как источник истины.

Readiness response содержит:

- `score`;
- `status`: `preliminary` или `report_backed`;
- `case_revision`;
- dimension contributions;
- gaps with impact;
- delta относительно предыдущей revision.

Канонические dimensions v1 берутся из существующего `StartupReadinessSnapshot`: `business_model`, `traction`, `unit_economics`, `market_evidence`, `gtm_evidence`, `risk_disclosure` и выбранные metric-pack dimensions.

Presentation score рассчитывается детерминированно:

```text
READY = 1.0
PROVISIONAL = 0.5
BLOCKED = 0.0
score = round_half_up(100 × сумма credit / число dimensions)
```

Правила статуса dimensions:

- совместимый `source_fact` или public research fact может дать `READY`;
- `founder_statement` с обязательными period/unit/declared source даёт максимум `PROVISIONAL`;
- детерминированный calculation получает `READY` только если все inputs source-backed; при наличии founder statement input получает максимум `PROVISIONAL`;
- AI-гипотеза, placeholder, unsupported inference и missing input дают `BLOCKED`;
- public benchmark не заполняет private startup input и влияет только на совместимый market/benchmark dimension;
- unresolved contradiction даёт `BLOCKED`; `resolved_by_founder` даёт максимум `PROVISIONAL`, пока не приложен source evidence;
- ни один экран не пересчитывает score из количества report sections;
- preliminary score явно подписан и не называется финальной инвестиционной оценкой;
- report-backed score доступен только при согласованных profile, GTM и report revision.

### 10.3 Clickable metric cards

Каждая metric card является настоящим control:

- при наличии значения открывает details/provenance;
- при missing input открывает structured fact drawer;
- при contradiction открывает reconciliation form;
- при calculation dependency объясняет формулу и недостающие inputs;
- при researchable benchmark предлагает подготовить safe research plan;
- при private fact не предлагает публичный поиск.

После сохранения UI показывает `что изменилось` и refresh соответствующих карточек без возврата в общий upload.

## 11. Постоянный UI Case Copilot

### 11.1 Размещение

- На широком desktop Case Copilot открывается как постоянная правая панель поверх существующей сетки.
- На меньшей ширине он становится drawer и не ломает текущую desktop-композицию.
- Состояние open/collapsed сохраняется локально для текущего пользователя.
- Header CTA `Спросить AI-советника` открывает тот же thread, а не отдельный экран с другим состоянием.
- Контекстные кнопки на Metrics, Market, Risks и Action Plan отправляют focus в этот же thread.

### 11.2 Содержимое панели

Панель показывает:

1. Название кейса и revision.
2. Краткое резюме текущего контекста.
3. Историю user/assistant/system events.
4. Один главный следующий шаг.
5. Реальные action cards с availability status.
6. Блок `Что изменилось` после выполненного действия.
7. Ссылки на evidence или research sources.

### 11.3 Поведение visible controls

Для каждой primary/secondary CTA действует одно из правил:

- control имеет рабочий handler и observable result;
- control disabled и рядом показана конкретная причина;
- control скрыт, если действие запрещено текущим policy.

Активная кнопка без handler или кнопка, которая только меняет подпись без доменного результата, запрещена acceptance-критерием.

## 12. Generated AI assets

### 12.1 Типы v1

- `customer_interview_script` — сценарий интервью и вопросы для проверки боли.
- `pricing_experiment` — гипотеза, варианты цены, сегменты, критерии успеха и guardrails.
- `positioning_map` — сравнение заявленного позиционирования с подтверждёнными alternatives.
- `weekly_funnel_template` — этапы воронки, определения и поля для еженедельного ввода.

### 12.2 API

```http
POST /cases/{case_id}/assets
GET  /cases/{case_id}/assets
GET  /cases/{case_id}/assets/{asset_id}
```

Создание принимает:

- `asset_type`;
- `expected_case_revision`;
- `idempotency_key`;
- пользовательское уточнение;
- разрешённые evidence refs;
- режим `draft`.

Ответ содержит status, preview, provenance и ограничения. Черновик хранится локально и доступен для повторной генерации. Interview, pricing и positioning assets скачиваются в Markdown; weekly funnel доступен в Markdown и CSV.

Кнопка `Собрать рабочий пакет` создаёт набор выбранных assets. Она не переводит пользователя на загрузку документов.

## 13. Batch improvement decisions

### 13.1 UX

- Каждая proposal card имеет локальное состояние `accepted`, `rejected` или `undecided`.
- До отправки пользователь может менять решения без backend mutation.
- Главная кнопка показывает число принятых, отклонённых и нерешённых proposals.
- Отправка невозможна, пока не принято решение по обязательному набору.
- После отправки отображаются version delta и recalculation result.

### 13.2 API

```http
POST /cases/{case_id}/advisor/improvements/decisions
```

Пример:

```json
{
  "base_version": 1,
  "proposal_set_hash": "sha256-of-the-current-six-proposals",
  "decisions": [
    {"proposal_id": "positioning", "decision": "accepted"},
    {"proposal_id": "monetization", "decision": "rejected"},
    {"proposal_id": "metrics", "decision": "accepted"},
    {"proposal_id": "go_to_market", "decision": "accepted"},
    {"proposal_id": "risk_reduction", "decision": "rejected"},
    {"proposal_id": "investment_readiness", "decision": "accepted"}
  ],
  "expected_case_revision": 8,
  "idempotency_key": "client-generated-uuid"
}
```

Операция:

- валидирует `base_version`, `proposal_set_hash` и точное равенство decision ids текущему полному proposal set;
- не применяет частичный mutation;
- создаёт одну новую improvement version;
- сохраняет accepted/rejected history;
- запускает один recalculation;
- возвращает before/after.

Application layer вводит отдельный `BatchImprovementDecisionCommand` и один `BatchImprovementRecalculationCommand` с полями `case_id`, `base_version`, `proposal_set_hash`, `accepted_ids`, `rejected_ids`, `expected_case_revision` и `idempotency_key`. Batch service не вызывает существующий single-proposal `apply_improvement` в цикле: он сначала атомарно сохраняет полный decision set и новую version, затем один раз вызывает batch recalculation port. Result содержит одну новую revision, одну improvement version и общий delta.

Кнопка `Вернуться к предыдущей версии` отображается только при наличии version history и вызывает отдельный подтверждённый restore command. Если history нет, интерфейс показывает причину, а не неактивную декоративную кнопку.

```http
POST /cases/{case_id}/advisor/improvements/versions/{version}/activate
```

Restore не переписывает историю. Он создаёт новую version на основе выбранной, требует `expected_case_revision` и `idempotency_key`, затем запускает один recalculation.

## 14. Error handling

| Ситуация | Обязательное поведение |
|---|---|
| Неполная ручная форма | Field-level ошибка рядом с конкретным полем; введённые значения сохраняются |
| Semantic mismatch | UI показывает недостающие части и пример; пользователь не должен угадывать regex |
| Stale revision | Возврат `409`; UI обновляет case context и предлагает повторить сохранение без потери draft |
| Duplicate command | Idempotent replay того же результата |
| LLM недоступен | Deterministic actions и формы продолжают работать |
| Research provider не настроен | Job получает `deferred` с понятной причиной и manual fallback |
| Research plan создан на старой revision | `409 stale_research_plan` до provider call либо `deferred/stale_research_plan` до evidence mutation; требуется re-plan |
| Часть источников недоступна | `partial`, список принятых/отклонённых источников и ограничения |
| Recalculation deferred | Fact/evidence сохранён, но UI честно показывает, что dependent snapshot ещё не обновлён |
| Asset generation failed | Черновик не объявляется созданным; доступен retry |
| Batch decision conflict | Никакая proposal не применяется частично |

Внешняя ошибка никогда не раскрывает локальные пути, raw document text, prompt, API key или внутренний traceback.

## 15. Privacy и audit invariants

1. Raw startup documents остаются локальными по умолчанию.
2. Research plan создаётся без внешнего вызова.
3. Consent запрашивается для каждого нового research job.
4. Наружу передаются только sanitized public queries.
5. Private metric values не подмешиваются в public query.
6. Public benchmark хранится отдельно от founder-confirmed fact.
7. Copilot message и asset clarification считаются `CONFIDENTIAL` по умолчанию и не становятся research query автоматически.
8. Любой внешний Copilot/Asset LLM call проходит существующий AI gateway, redaction, minimization, audit, budget и case policy; raw document и полный transcript остаются локальными.
9. Research plan и job жёстко привязаны к `case_id`, `case_revision` и `plan_hash`; stale result не меняет evidence.
10. Manual evidence имеет локальный `founder_manual_input` artifact и не маскируется под загруженный source artifact.
11. Любая mutation пишет локальный audit event с `case_id`, revision, action type, actor и founder-safe result.
12. Источник, расчёт, вывод и AI-гипотеза остаются разными типами.
13. Generated asset не является evidence.

## 16. Data flow по ключевым сценариям

### 16.1 Разрешение MRR-противоречия

```text
Copilot видит open MRR contradiction
  → предлагает open_fact_input(mrr)
  → UI показывает amount + scale + currency + period + source
  → founder сохраняет working value
  → CaseFactIntakeService добавляет evidence и resolution
  → новая revision
  → same-case recalculation
  → MRR/ARR/readiness/conflict delta
  → Copilot system event «что изменилось»
```

Публичный research в этом сценарии не предлагается.

### 16.2 Пустой market screen

```text
Market card просит подтверждённые источники
  → Copilot предлагает prepare_public_research
  → plan показывает sanitized queries и manual-only gaps
  → founder даёт consent
  → research job получает публичные sources
  → SafeResearchService обновляет market evidence
  → новая revision и dependent recalculation
  → Market, readiness и recommendations показывают delta
```

### 16.3 Пользователь не знает ответ

```text
Copilot задаёт вопрос
  → пользователь отвечает «не знаю»
  → registry проверяет researchability
  ├─ public context разрешён → research plan
  └─ private fact → объяснение + manual/file template
```

Система не выдумывает private value и не блокирует весь проект. Gap остаётся видимым, а пользователь получает следующий допустимый способ продвижения.

### 16.4 Подготовка рабочего материала

```text
Action Plan → «Подготовить pricing-тест»
  → CaseAssetService получает текущую revision и evidence refs
  → строит локальный draft
  → UI открывает preview
  → пользователь сохраняет/перегенерирует/скачивает
```

## 17. Планируемые кодовые границы

Точные файлы будут зафиксированы implementation plan после review спецификации. Предпочтительная декомпозиция:

### Backend

- новые небольшие application services для fact intake, copilot, research jobs и assets;
- typed domain models вместо расширения одного большого advisor service;
- новые API request/response models и routes в startup router;
- reuse существующего case coordinator, Evidence Ledger, research adapters и advisor recalculation port;
- локальные repository ports для copilot thread, research job и asset metadata, реализованные поверх текущего storage pattern;
- отдельные contract/unit/API tests на каждый command.

### Frontend

- `CaseCopilotPanel` как отдельный компонент;
- `CaseFactDrawer` и registry-driven input controls;
- research plan/consent/job status components;
- generated asset preview;
- batch improvement decision state;
- расширение typed API client/contracts;
- тонкая интеграция в FounderShell и существующие pages без переноса всей логики в эти крупные файлы.

Frontend должен сначала прочитать и соблюдать `frontend/founder/AGENTS.md`.

## 18. Delivery roadmap

Спецификация реализуется не одним большим diff, а шестью проверяемыми вертикальными slices.

### Slice 0 — Contract freeze и RED tests

Результат:

- утверждённые request/response contracts;
- API/front-end parser tests;
- failing integration tests на dead CTAs и отсутствующие data flows;
- зафиксированные privacy invariants.

Stop condition: RED доказан ожидаемыми причинами, production code ещё не изменяет поведение.

### Slice 1 — Structured intake и readiness

Результат:

- fact requirements API;
- `POST /facts`;
- contextual metric/reconciliation drawer;
- same-case delta;
- preliminary/report-backed readiness;
- кликабельные metric cards.

Stop condition: ручной ввод MRR, burn и cash обновляет тот же кейс, метрики и readiness без общего upload redirect.

### Slice 2 — Safe research plan и jobs

Результат:

- двухшаговый prepare/consent flow;
- production provider-backed market research с deterministic cited fake для CI/integration proof;
- job statuses и sources;
- единый вызов из Upload, Market, Advisor и Copilot entry points.

Stop condition: deterministic cited provider в CI доказывает `job → sources → market evidence → revision/readiness delta`, а unconfigured provider доказывает `deferred` без evidence mutation и ложного success. При наличии credential отдельный live smoke подтверждает production adapter; private metric остаётся manual-only.

### Slice 3 — Persistent Case Copilot

Результат:

- локально сохраняемый thread;
- context-aware messages;
- typed actions;
- persistent right panel/drawer;
- deterministic fallback;
- system events с before/after.

Stop condition: на двух разных fixtures Copilot задаёт разные gap-driven вопросы и выполняет реальные actions.

### Slice 4 — Assets и batch improvements

Результат:

- четыре asset types с preview/download;
- рабочий `Собрать пакет`;
- batch proposal decisions;
- version history и conditional restore;
- один recalculation на batch.

Stop condition: все видимые CTA данного контура имеют observable result или явный blocker reason.

### Slice 5 — End-to-end hardening

Результат:

- same-case browser journey;
- second-fixture anti-hardcode comparison;
- restart/replay tests;
- privacy and audit proof;
- regression suite, typecheck, lint и final verification note.

Stop condition: пользователь может проследить полный путь `input/research → evidence → recalculation → metrics/readiness/action change`.

## 19. Acceptance criteria

### 19.1 Structured intake

- MRR contradiction form явно просит value, currency, scale, period и source.
- Ответ `28.6m KZT за июль 2026, источник CRM` проходит без необходимости угадывать hidden regex.
- Неполный ответ показывает конкретно отсутствующий элемент.
- Сохранение создаёт новую revision и founder-safe delta.
- Старые конфликтующие observations остаются в lineage.

### 19.2 Metrics/readiness

- MRR, burn, cash, churn, retention, CAC и margin cards открывают контекстное действие.
- Burn + cash позволяют рассчитать runway детерминированно.
- Readiness не равен необъяснимому `0` только из-за отсутствия отчёта.
- Score имеет status, factors, gaps и revision.
- После нового факта UI показывает before/after.

### 19.3 Safe research

- `Подготовить безопасный ресерч` создаёт видимый plan, а не локальный toggle.
- До consent нет внешнего вызова.
- После consent разрешённая market/competitor задача вызывает injected provider; CI использует deterministic cited fake, production — настроенный live adapter.
- Результат содержит источники и список обновлённых блоков.
- Попытка исследовать private MRR блокируется до provider call и объясняет manual/file путь.
- Без credential обязательная ветка доказывает `deferred` без evidence mutation; статус live-verified ставится только после smoke через реально настроенный provider и разрешённый egress.

### 19.4 Copilot

- Thread сохраняется после reload и restart.
- Header и contextual CTAs открывают один и тот же case thread.
- Copilot знает текущий page context и revision.
- Предложенное действие имеет реальный handler либо blocker reason.
- При недоступном LLM формы и детерминированные рекомендации продолжают работать.
- Второй fixture не получает название, метрики или вопросы первого кейса.

### 19.5 Assets и improvements

- Каждая кнопка `Подготовить` создаёт реальный preview.
- `Собрать рабочий пакет` не открывает upload.
- Шесть proposal decisions отправляются batch-запросом.
- Batch создаёт одну version и один recalculation.
- Повторный idempotency key не создаёт вторую version.

### 19.6 UI integrity

- Нет активной primary CTA без observable result.
- Disabled control всегда имеет понятную причину.
- Не показывается запрещённый answer mode.
- Визуальные токены, типографика, цвета, радиусы и общий layout остаются совместимыми с текущим Founder Workspace.
- Новая правая панель не создаёт horizontal overflow на поддерживаемом desktop viewport.

## 20. Проверки

Минимальная evidence matrix для каждого slice:

| Уровень | Проверка |
|---|---|
| Domain/unit | Validation, privacy classification, state transition, idempotency, batch atomicity |
| Application | Fact → evidence → revision → recalculation delta; research plan → job → evidence |
| API | Typed request/response, 409 stale revision, 422 field errors, no leakage |
| Frontend unit | Contract parsers, control availability, draft preservation, before/after presentation |
| Component | Drawer, Copilot actions, job states, asset preview, batch decisions |
| Browser E2E | NomadFlow same-case path и второй fixture anti-hardcode path |
| Static/regression | Backend focused/full tests, frontend tests, typecheck, lint, privacy checks |

Критические browser scenarios:

1. Upload NomadFlow → MRR contradiction → structured answer → metrics/readiness delta.
2. Market empty state → research plan → consent → completed/partial sources → market delta.
3. Metrics → burn + cash → deterministic runway.
4. Copilot `не знаю` → корректное разделение manual-only и researchable context.
5. Action Plan → pricing asset preview.
6. Improvements → six decisions → one version bump.
7. Restart → thread, job и assets доступны.
8. Second fixture → другие факты, вопросы, research scope и метрики.

## 21. Риски и меры

| Риск | Мера |
|---|---|
| Copilot превращается в второй источник истины | Только typed actions могут менять case state; thread хранит ссылки, а не копии канонических фактов |
| UI снова обещает больше backend | Contract tests для availability и запрет active control без handler |
| Утечка private context в research | Двухшаговый plan/consent, allowlist, sanitize и audit до provider call |
| Огромные существующие frontend files становятся ещё больше | Новые focused components и services; shell только связывает callbacks/state |
| Новый parallel revision mechanism | Полный reuse существующего `data_revision` и advisor recalculation boundary |
| Асинхронный research теряется при restart | Job metadata сохраняется локально; `running` после restart становится `deferred/research_interrupted` и требует явного retry |
| LLM ломает core workflow | Deterministic requirements, gaps, validation, formulas и actions остаются без LLM |
| Batch decisions конфликтуют со старой версией | `base_version`, `expected_case_revision`, atomic validation и idempotency |
| Readiness снова выглядит выдуманной | Публичные factor contributions, source types, gaps и revision |

## 22. Решения, принятые в спецификации

- Один Copilot thread на кейс.
- Non-streaming response в v1; streaming не является блокером.
- Research асинхронный и локально сохраняемый.
- Подготовка research plan не требует consent и не делает внешний вызов.
- Запуск каждого job требует отдельного consent.
- Private metrics всегда manual/file only; допустим только публичный benchmark как отдельный тип контекста.
- Все mutations versioned, idempotent и same-case.
- Copilot не пишет facts напрямую.
- Readiness существует до report как `preliminary`, после согласованного отчёта как `report_backed`.
- Improvement decisions применяются batch-операцией.
- Generated assets являются drafts, а не evidence.
- Текущий visual language сохраняется; основной UX-ремонт — рабочие data flows, context и feedback.

## 23. Implementation handoff boundary

После review владельца эта спецификация декомпозируется в отдельные implementation plans по вертикальным slices. Первый исполнимый plan должен покрывать Slice 0 и Slice 1, потому что structured fact intake и единая revision/recalculation цепочка являются foundation для research, Copilot, assets и improvements.

До утверждения written spec не начинается изменение production code по Case Copilot v1.

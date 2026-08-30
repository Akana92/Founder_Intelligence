# Founder Intelligence: динамический анализ документа и честные метрики

> **For agentic workers:** Execute this plan step-by-step. Keep the accepted dark Founder Intelligence UI direction. Do not roll back unrelated WIP. Do not create a branch or worktree. Make behavior evidence-driven, not demo-hardcoded.

## Цель

Пользовательский сценарий должен доказуемо реагировать на загруженный startup-документ:

- первая страница показывает, что именно было понято из документа;
- Gate 2/Profile не остаётся на плейсхолдерах, если документ содержит продукт, клиента, проблему, монетизацию или стадию;
- overview/metрики показывают coverage/evidence/progress из текущего кейса, а не визуальные константы;
- AI-вопрос выбирается из реального пробела профиля, а не всегда из фиксированного первого вопроса;
- после ответа сохраняется same-case recalculation path без утечки приватного текста в UI.

## Ограничения

- Не менять принятую визуальную концепцию: тёмный premium Founder Workspace, розовый акцент, карточная композиция.
- Не добавлять новый параллельный demo-state на фронте.
- Не откатывать чужие изменения в грязном worktree.
- Не подключать внешние web/API-исследования без отдельного разрешения.
- Не считать это закрытием всего Task 8 из старого handoff, пока не пройден полный PDF → Gate 4 → reports → Admin trace путь.

## Этап 1 — Backend: извлечение фактов из русскоязычного startup-документа

Success criteria:

- `DeterministicStartupProfileExtractor` извлекает русские бизнес-поля: название, продукт/описание, проблема, решение, ICP/клиент, стадия, модель выручки, GTM/каналы, конкуренты.
- Извлечённые значения проходят существующую санитизацию и не возвращают пути, токены, email/raw private fragments.
- Существующие unit-тесты extractor не регрессируют.

Implementation:

1. Добавить failing unit-test с русскоязычным бизнес-планом.
2. Расширить label-map и matching на `:`, `-`, `—`.
3. При необходимости добавить безопасный section/prose fallback для поля продукта.
4. Запустить targeted pytest по extractor.

## Этап 2 — Backend: AI-вопрос из реального пробела профиля

Success criteria:

- Если revenue/pricing уже подтверждён из документа, первый advisor-вопрос не должен снова спрашивать revenue; он должен перейти к следующему существенному пробелу, например ICP.
- Если профиль полностью пустой, текущий порядок вопросов сохраняется.
- Порядок вопросов фиксируется в case-state, чтобы recalculation/replay не ломали историю.
- Same-case recalculation после ответа остаётся существующим backend-контрактом.

Implementation:

1. Добавить failing unit-test на profile-aware question selection.
2. Добавить безопасное вычисление question-order из текущего startup profile.
3. Передавать этот порядок в replay/next/apply.
4. Сохранять order в advisor state.
5. Запустить targeted pytest по advisor API.

## Этап 3 — Frontend: честное отображение coverage, inventory и progress

Success criteria:

- Presentation model отдаёт coverage/evidence-backed/missing/contradiction counts из реального профиля.
- Overview/Gate 2 показывают coverage и source/evidence inventory, а не только абстрактную confidence.
- Progress на агентских карточках считается из текущей стадии/шага, а не из литерала `29%` / `2 из 7`.
- UI всё ещё fails closed: нет score/progress, если нет данных.
- Callback/navigation-контракты сохраняются.

Implementation:

1. Добавить frontend unit/source tests на coverage presentation и отсутствие hardcoded progress.
2. Расширить `profile-presentation` вычисляемыми founder-safe метриками.
3. Обновить `founder-analysis-pages` так, чтобы summary/progress брались из workspace/profile/report snapshot.
4. Запустить targeted frontend tests, затем typecheck/lint/build по возможности.

## Этап 4 — Проверка на synthetic startup-документе

Success criteria:

- Используем существующий тестовый документ `docs/demo/test-startup/flowpilot-ai-synthetic-startup-plan.pdf` или `.docx`.
- Backend extractor/advisor tests проходят.
- Frontend presentation/source tests проходят.
- Если полный browser/API smoke не запускается в текущей среде, это явно указано как validation gap, без заявления о полном Task 8 completion.

## Stop condition

Остановиться, когда реализованы и проверены этапы 1–3 targeted tests + доступная сборочная проверка. Если полный E2E остаётся не запущен, финальный отчёт должен честно отделить выполненную динамику UI от полного закрытия старого Task 8.

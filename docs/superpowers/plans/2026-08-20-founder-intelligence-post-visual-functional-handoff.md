# Founder Intelligence — post-visual functional handoff

Дата актуализации: 2026-08-20

Рабочая папка: `D:\Agents\Projects\Capstone N3`

Ветка: `main`

## 1. Назначение документа

Это самое новое операционное уточнение для продолжения проекта в новом чате после постраничной проверки Founder Workspace владельцем.

Документ не заменяет продуктовое ТЗ и базовый delivery roadmap. Он фиксирует изменившийся порядок работы, текущую точку продолжения и то, что уже нельзя начинать заново.

Если более ранний handoff, `design-qa.md` или verification-документ противоречит этому checkpoint в вопросах текущей визуальной приёмки и следующего этапа, использовать этот документ как более новое уточнение.

## 2. Канонические документы

Перед изменениями полностью прочитать:

1. `docs/superpowers/specs/2026-08-11-founder-launch-intelligence-product-tz.md`, особенно раздел 34;
2. `docs/superpowers/plans/2026-08-11-founder-launch-intelligence-delivery-roadmap.md`;
3. `docs/superpowers/plans/2026-08-16-founder-ai-advisor-ux-completion.md`;
4. `.superpowers/sdd/2026-08-16-founder-ai-advisor-ux-completion/progress.md`;
5. отчёты Tasks 0–7 в `.superpowers/sdd/2026-08-16-founder-ai-advisor-ux-completion/`;
6. `.superpowers/sdd/2026-08-16-founder-ai-advisor-ux-completion/task-8-brief.md`;
7. `docs/verification/2026-08-17-founder-e2e-screen-transition-matrix.md`;
8. `START_NEW_CHAT_HERE.md` — как полный набор архитектурных, privacy, Git и capstone-ограничений, но с учётом overrides из этого checkpoint.

Перед любым изменением `frontend/founder` полностью прочитать `frontend/founder/AGENTS.md`.

## 3. Что изменилось относительно старого handoff

Старый статус:

`owner_visual_acceptance = rejected`

был исходной границей перед большой визуальной переработкой. Он больше не описывает текущее состояние Founder Workspace.

Актуальный статус:

- `founder_workspace_screen_by_screen_review = accepted_for_functional_integration`;
- `admin_console_visual_review = provisional_owner_follow_up`;
- `fresh_14_state_regression_capture = pending`;
- `task_8_fresh_acceptance = pending`.

Владелец последовательно проверял реальные localhost-экраны и давал точечные замечания по типографике, композиции, графикам, иконкам, маршрутам и центрированию. После исправлений Founder-экраны были разрешены к дальнейшей работе. Их нельзя снова открывать как новый арт-дирекшн или переделывать с нуля без новой визуальной регрессии или прямого замечания владельца.

Admin Console была существенно улучшена, но владелец отдельно отметил, что к ней ещё вернётся. Поэтому экран 10 не считается окончательно визуально замороженным.

## 4. Изменённый порядок экранов

Канонический demo-маршрут:

`01 → 02 → 03 → 04 → 11 → 12 → 13 → 14 → 05 → 06 → 07 → 08 → 09 → 10`

Расшифровка:

| Экран | Состояние |
| --- | --- |
| 01 | Старт / загрузка материалов |
| 02 | Data Room / запуск анализа |
| 03 | Прогресс агентов и Gate 2 |
| 04 | Обзор проекта и readiness |
| 11 | Следующий лучший вопрос AI-советника |
| 12 | Ответ вручную, файлом, разрешённым поиском или пропуск |
| 13 | Обновлённый анализ после ответа |
| 14 | Улучшенный план и решения по предложениям |
| 05 | Метрики и финансы |
| 06 | Рынок и конкуренты |
| 07 | Риски, противоречия и вопросы |
| 08 | План действий и Gate 3 |
| 09 | Report Center и Gate 4 |
| 10 | Streamlit Admin Console того же `case_id` |

AI-советник намеренно расположен сразу после первичного обзора. Пользователь сначала уточняет наиболее важный пробел, затем видит пересчитанные метрики, рынок, риски и план.

## 5. Что уже сделано и не должно переделываться

- Queue 1–4 закрыты для frozen/offline scope.
- Tasks 0–7 Founder AI Advisor завершены и имеют отчёты.
- Реализован настоящий consent-gated public web research path с источниками, privacy boundary, budget/timeout/outage fallback. Его нельзя снова описывать как отсутствующий.
- Реализованы четыре режима ответа советнику: вручную, файлом, разрешённым публичным поиском и пропуском.
- Реализованы шесть детерминированных областей улучшений, accept/reject decisions и version lineage.
- Реализованы founder-safe русские JSON/HTML/PDF projections.
- Существует исторический Queue 5 evidence packet от 2026-08-16. Он подтверждает старый frozen checkpoint, но не заменяет свежую проверку после текущего WIP.
- Текущий UI и backend WIP сохраняются. Не применять `git reset`, `git checkout`, `git clean`, broad delete или автоматическое восстановление старых файлов.
- Не начинать R11/R12.
- Не создавать новую ветку или worktree.

## 6. Текущая рабочая точка

На момент создания checkpoint:

- HEAD: `4c76a2a84da4a757f186478fb02ae39a37189779`;
- ветка: `main`;
- поверх `ab403fc49542f44730a382b011d29c1d1398507a` находятся два понятных docs-only handoff-коммита;
- в рабочем дереве большой незакоммиченный WIP Founder UI, Admin, LangGraph, API, reports, tracing и tests;
- этот WIP нельзя откатывать или перезаписывать вслепую.

Последняя проверенная техническая граница перед новым функциональным этапом:

- свежий frontend test run имеет пять падающих assertions в `founder-workspace-controller.test.ts`; сначала определить, являются ли они устаревшими контрактами после UI-реорганизации или настоящими регрессиями;
- full 14-state screenshot capture дошёл до экрана 06 и остановился на вертикальном overflow `4px` при tolerance `1px`;
- targeted backend run прошёл 74 теста, но не дал чистый итоговый PASS из-за Windows temp/permission cleanup;
- свежие полные `typecheck`, `lint`, `build`, backend pytest, Ruff и strict mypy после всего WIP ещё не доказаны;
- `design-qa.md`, progress и старые owner-rework документы частично отстают от фактической постраничной проверки.

Эти числа являются наблюдаемым checkpoint от 2026-08-20. Перед исправлением их нужно перепроверить, а не считать вечными.

## 7. Что должен сделать новый чат

### Этап A — стабилизировать уже принятый UI

1. Прочитать этот checkpoint и обязательные документы.
2. Выполнить fresh Git status/diff без изменения или очистки WIP.
3. Перезапустить frontend tests и исправить только подтверждённые регрессии.
4. Устранить `4px` overflow экрана 06 без визуального редизайна принятой композиции.
5. Выполнить `npm test`, `npm run typecheck`, `npm run lint`, `npm run build`.
6. Снять все 14 состояний при `1440×1000` в каноническом порядке и собрать contact sheet.
7. Не объявлять Admin окончательно принятым. Для Founder Workspace не открывать новый дизайн-цикл при отсутствии регрессии.
8. После доказательств синхронизировать `design-qa.md`, progress и verification status.

### Этап B — доказать настоящий сквозной пользовательский путь

Использовать существующие callbacks/API и один настоящий private `case_id`:

`PDF upload → document processing → primary profile → Gate 2 → overview → advisor question → advisor answer → same-case recalculation → improved proposals → metrics → market → risks → Gate 3 → action plan → Gate 4 → same-case JSON/HTML/PDF → Admin trace`

Не создавать параллельный frontend demo state. Все видимые переходы должны быть результатом backend/graph state.

Первый функциональный RED/verification gap:

> Ответ советнику или принятие предложения должны запустить canonical recalculation того же `case_id`, инвалидировать устаревший report lineage, создать новую версию анализа/отчёта и после рестарта продолжиться без повторного внешнего вызова.

После этого последовательно доказать:

1. настоящий LangGraph interrupt/resume Gate 2;
2. четыре режима ответа советнику;
3. обновлённый анализ без выдуманных изменений;
4. accept/reject/version lineage шести предложений;
5. Gate 3 с явным решением по противоречиям;
6. Gate 4 с same-case JSON/HTML/PDF;
7. Admin trace того же `case_id`.

### Этап C — доказать учебную границу autonomous multi-agent system

В работающем кейсе и Admin должны быть видны:

- реальный typed LangGraph Plan-and-Execute;
- Document, Profile, Product, Metrics, Market, Financial, Risk, Critic, Arbiter, GTM и Report как реальные исполнители;
- bounded Critic/Arbiter Reflexion максимум в два раунда;
- минимум три разные typed tool boundaries: document/OCR/storage, локально перепроверяемый расчёт, consented public web search;
- start/status/duration/retries/timeout/result/error каждого tool invocation;
- один outage/timeout с fallback или replanning;
- Gate 2, Gate 3 и Gate 4 pause/resume;
- restart-safe продолжение одного кейса;
- local audit как source of truth;
- sanitized LangSmith trace с token/cost evidence без raw documents, filenames, paths, prompts, PII, secrets или chain-of-thought.

### Этап D — повторно закрыть Task 8

Только после полного offline GREEN:

1. fresh Gates B/C/D-A/D-B/E;
2. полный backend pytest, Ruff, strict mypy;
3. privacy, determinism, restart, failure matrix и report/trace lineage;
4. один sanitized LangSmith smoke при наличии `LANGSMITH_API_KEY`;
5. один bounded OpenAI competitor-synthesis smoke при наличии `OPENAI_API_KEY` и бюджете `<= $0.25`;
6. demo script на 7–10 минут;
7. карта `требование ТЗ → действие в демо → файл/trace/screenshot/test`;
8. независимый code/docs/visual/acceptance review;
9. маленькие сфокусированные коммиты только через явный `git add -- <paths>`.

Отдельный live Research Agent web smoke не запускать без нового явного разрешения владельца.

## 8. Продуктовая правда, которую нельзя нарушать

- Не показывать выдуманные проекты, имена, MRR/ARR, проценты, риски, конкурентов, источники или успешные статусы.
- Не показывать founder-пользователю `MISSING`, block IDs, hashes, trace IDs, filenames, local paths, raw PDF text, prompts, secrets, PII или internal reason codes.
- Если данных нет, объяснять пользу следующего шага, а не создавать тупик.
- Подходящая формулировка:

> Если вы добавите X, я смогу уточнить Y и рассчитать Z. Либо, после вашего разрешения, могу найти публичные источники вместо вас.

- Неподдерживаемые действия должны быть disabled.
- Offline Gates не зависят от сети или tracing export.
- Live inference не называть live web research.
- Local audit работает даже при недоступности LangSmith.
- Desktop only, целевой viewport `1440×1000`.

## 9. Что новый чат не должен делать

- Не начинать снова с просмотра и переделки всех 14 макетов.
- Не объявлять визуальный PASS только на основании unit tests.
- Не объявлять Task 8 или Queue 5 повторно закрытыми до свежих доказательств.
- Не заменять backend workflow статическими frontend-объектами.
- Не выполнять произвольные внешние web-вызовы.
- Не печатать значения API keys.
- Не добавлять runtime/temp/screenshot artifacts в Git.
- Не изменять или добавлять в Git защищённые пользовательские файлы, перечисленные в `START_NEW_CHAT_HERE.md`.

## 10. Критерий завершения следующего этапа

Новый этап завершён, когда владелец может пройти один реальный startup case от PDF до финального отчёта по утверждённому порядку экранов, увидеть настоящие паузы и решения Gate 2/3/4, получить обновлённый анализ после ответа советнику, открыть JSON/HTML/PDF того же case и показать в Admin технический trace этого же запуска без утечки приватных данных.

Зелёные тесты без этого browser/API journey недостаточны. Красивые скриншоты без настоящего graph/API workflow также недостаточны.

## 11. Как начать новый чат

Первое сообщение новому чату:

> Продолжи Capstone N3 из `docs/superpowers/plans/2026-08-20-founder-intelligence-post-visual-functional-handoff.md`. Прочитай документ полностью и следуй указанному в нём source order. Не начинай визуальную работу заново и не откатывай существующий WIP. Сначала восстанови Git/status, перепроверь текущие regressions, затем продолжи функциональный E2E и Task 8 автономно.

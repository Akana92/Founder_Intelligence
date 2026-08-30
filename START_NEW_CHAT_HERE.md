# Единый промт для продолжения Capstone N3 в новом чате

> **АКТУАЛЬНЫЙ CHECKPOINT ОТ 2026-08-25 (имеет приоритет над старым текстом ниже):**
> сначала полностью прочитай `docs/handoffs/2026-08-24-capstone-n3-docker-packaging-handoff.md`.
> Текущая проверенная ветка — `codex/case-copilot-docker` в worktree
> `C:\Users\Akana\.codex\worktrees\6e2b\Capstone N3`. Case Copilot v1, русифицированный
> Founder Workspace, API и опциональная админка уже упакованы через Docker Compose и
> проверены из чистого клона. Не повторяй принятые задачи и не переходи автоматически в
> `D:\Agents\Projects\Capstone N3`: его `main` сохранён нетронутым, но содержит большой
> пересекающийся dirty WIP, поэтому локальный merge пока небезопасен. Не делай reset,
> clean, checkout, revert, stash, merge, push, deploy или публикацию образов без проверки
> актуального handoff и отдельного разрешения на внешние действия.

Скопируй в новый чат всё содержимое этого файла целиком. Отдельные UI- и product-logic-промты больше не нужны.

> **Последнее обязательное уточнение от 2026-08-20:** перед выполнением этого handoff полностью прочитай `docs/superpowers/plans/2026-08-20-founder-intelligence-post-visual-functional-handoff.md`. Этот checkpoint является более новым источником текущего visual-acceptance статуса, изменённого порядка продолжения и границы Task 8. Разделы ниже, где UI всё ещё обозначен как `owner_visual_acceptance = rejected`, описывают исходную границу до постраничной переработки и не являются командой начинать дизайн заново.

---

Продолжи разработку Investment Due Diligence / Founder Intelligence в рабочей папке:

`D:\Agents\Projects\Capstone N3`

Работай автономно в ветке `main`. Не создавай новую ветку и не используй существующие worktree или feature-ветки.

## 1. Сначала восстанови точный контекст

Полностью прочитай, прежде чем менять файлы:

1. `README.md`
2. `PRODUCT.md`
3. `DESIGN.md`
4. `docs/superpowers/specs/2026-08-11-founder-launch-intelligence-product-tz.md`, особенно раздел 34
5. `docs/superpowers/plans/2026-08-11-founder-launch-intelligence-delivery-roadmap.md`
6. `docs/superpowers/plans/2026-08-16-founder-ai-advisor-ux-completion.md`
7. `.superpowers/sdd/2026-08-16-founder-ai-advisor-ux-completion/progress.md`
8. отчёты Tasks 0–7 в `.superpowers/sdd/2026-08-16-founder-ai-advisor-ux-completion/`
9. `.superpowers/sdd/2026-08-16-founder-ai-advisor-ux-completion/task-8-brief.md`
10. `docs/superpowers/plans/2026-08-20-founder-intelligence-post-visual-functional-handoff.md`
11. `mockups/founder-intelligence-desktop/README.md`
12. все 14 PNG из `mockups/founder-intelligence-desktop/`, от `01-*.png` до `14-*.png`

Перед любым изменением `frontend/founder` отдельно и полностью прочитай `frontend/founder/AGENTS.md`.

Используй доступные дизайн-навыки `product-design:image-to-code`, `impeccable`, `ui-ux-pro-max`, `ui-styling` и `playwright-cli`. Они нужны не для нового арт-направления, а для точного переноса уже утверждённых макетов, визуального сравнения и проверки настоящего localhost-интерфейса.

После чтения выполни:

```powershell
git status --short --branch
git rev-parse HEAD
git log -8 --oneline
git diff --stat
git diff -- frontend/founder src/due_diligence_agent/presentation/streamlit/components/audit.py tests/smoke/test_streamlit_admin_console.py
```

Базовый HEAD непосредственно перед объединением handoff-промтов:

`ab403fc49542f44730a382b011d29c1d1398507a`

Поверх него ожидается один docs-only commit с этим единым handoff-промтом. Допускаются только более новые понятные коммиты того же проекта. Конкретно объясни любое иное расхождение. Не откатывай и не перезаписывай незакоммиченный WIP.

## 2. Обязательная учебная граница: Autonomous Agent / Multi-Agent System

Этот проект сдаётся не как красивый dashboard и не как генератор статического отчёта. Он обязан на работающем пользовательском кейсе доказать требования учебного ТЗ «Автономные AI-Агенты и Мультиагентные Системы».

Обязательная архитектура и наблюдаемое поведение:

- реальный типизированный LangGraph state graph управляет планом, зависимостями, ветвлением, остановками, возобновлением и завершением кейса;
- основной паттерн — Plan-and-Execute; Critic и Arbiter выполняют bounded Reflexion/self-correction с поиском противоречий и максимум двумя итерациями; ReAct допустим внутри инструментального шага, но не требуется как единственный паттерн;
- специализированные роли Document, Profile, Product, Metrics, Market, Financial, Risk, Critic, Arbiter, GTM и Report должны быть реальными узлами/исполнителями с видимым progress и trace, а не декоративными названиями;
- входы и выходы агентов и инструментов валидируются Pydantic-схемами;
- через controlled Function Calling или эквивалентный типизированный tool invocation должны быть продемонстрированы минимум три разнородные границы инструментов: consented public Web Search с источниками, Python/Code Interpreter или локально перепроверяемый расчёт, а также document/OCR/data-storage инструмент; несколько обёрток одного API не считать разными инструментами;
- для каждого инструмента видны запуск, статус, длительность, retries, timeout, результат или безопасный код ошибки;
- timeout, provider outage, исчерпание бюджета и невалидный ответ не рушат кейс: граф выполняет fallback/replanning и продолжает на разрешённых cached/local данных;
- Human-in-the-Loop реализован настоящими LangGraph interrupt/resume checkpoints: как минимум Gate 2 перед внешней передачей/глубоким анализом, Gate 3 для решения по противоречиям и Gate 4 перед заморозкой финального отчёта;
- после рестарта пользователь продолжает тот же case/checkpoint без повторного внешнего вызова и без потери решения;
- Founder Workspace показывает понятные статусы «анализирую документы», «рассчитываю метрики», «проверяю противоречия», «ищу публичные источники», «ожидаю вашего решения»; Streamlit Admin отдельно показывает технический граф, tools, retries, errors, cost и lineage;
- LangSmith получает реальный sanitized trace одного startup workflow с узлами, длительностью, retries, ошибками, gates, token usage и cost; raw документы, prompts, PII, secrets и chain-of-thought не экспортируются;
- local audit остаётся источником истины и продолжает работать при недоступности LangSmith;
- edge cases, tool outages, privacy, budgets, loop limits и HITL pause/resume должны иметь тесты и видимое доказательство для защиты.

Выбранный продуктовый профиль остаётся гибридным: Founder Workspace реализован на Next.js, а техническая Admin Console — на Streamlit. Это соответствует утверждённому проектному ТЗ и сохраняет обязательную Streamlit-поверхность для наблюдаемости.

Для финальной защиты подготовь отдельную карту `требование учебного ТЗ → действие в демо → файл/trace/screenshot/test`, где проверяющий увидит:

1. построение и выполнение плана в LangGraph;
2. три разных реальных tool boundaries;
3. одну bounded Reflexion/self-correction петлю;
4. настоящую HITL pause/resume точку;
5. один отказ инструмента с fallback/replanning;
6. sanitized LangSmith trace с token/cost evidence;
7. UI-статусы работающих агентов;
8. итоговый same-case отчёт и документацию edge cases.

UI-проверка по 14 макетам не заменяет эту функциональную границу. В свою очередь, наличие LangGraph и тестов не заменяет визуальную приёмку владельцем — обе части обязательны.

## 3. Критическая корректировка после проверки владельцем

Текущий UI **не принят владельцем**.

Владелец проверил реальные страницы на `http://127.0.0.1:3000/` и Admin на `http://127.0.0.1:8501/` и явно отклонил визуальный результат. Нельзя считать UI завершённым, почти готовым или требующим только небольшого polish.

Что именно не устроило владельца:

- реализация сильно отличается от утверждённых макетов;
- была просмотрена и перенесена лишь часть из 14 состояний;
- правильное направление палитры не компенсирует слабую композицию;
- типографика, размеры, межстрочные интервалы и визуальная иерархия слабее макетов;
- отступы, сетка, ширины колонок и плотность контента не совпадают;
- тени, стеклянные поверхности, границы и глубина выглядят плоско;
- карточки, кнопки, иконки и графики выглядят как технические заготовки;
- на ряде экранов слишком много пустого пространства и нарушен масштаб;
- Founder Workspace и Admin Console визуально не достигают уровня утверждённого демо.

Предыдущие утверждения «не начинай UI заново», «UI checkpoint почти готов» и `blocked_pending_owner_screenshots` больше не действуют. Новая истинная граница:

`owner_visual_acceptance = rejected`

Текущий код и WIP нужно сохранить как рабочую техническую базу, но визуальный слой разрешено существенно переработать и реорганизовать. Не откатывай WIP вслепую и не ломай реальные callbacks/API.

## 4. Утверждённая UI-граница

- Все 14 desktop-макетов являются источником истины. Нельзя ограничиться пятью экранами.
- Канонический порядок демо: `01 → 02 → 03 → 04 → 11 → 12 → 13 → 14 → 05 → 06 → 07 → 08 → 09 → 10`.
- Целевой viewport для реализации и проверки: `1440×1000`.
- Desktop only. Мобильную версию не делать, не тестировать и не добавлять.
- Нужна screen-by-screen, pixel-level близость по сетке, масштабу, типографике, карточкам, теням, графикам и состояниям, а не только похожая палитра.
- Левая панель, рабочая область, карточки, верхние действия и информационная плотность должны повторять композицию соответствующего макета.
- Визуальный язык: тёмный чёрно-графитовый фон, дымчато-розовый/фиолетовый свет, качественные стеклянные панели, тонкие границы, мягкая глубина и аккуратные data visualizations.
- Полностью убрать из доступного пользовательского пути старый cyan terminal/dossier UI.
- Не использовать имя `Алексей` или любое выдуманное имя. На стартовом экране оставить только `Добро пожаловать`.
- Не показывать выдуманные проекты, проценты готовности, MRR/ARR, риски, источники или успешные статусы.
- Founder UI не показывает `MISSING`, document block IDs, hashes, raw trace IDs, local paths, filenames, raw PDF text, prompts, secrets, PII или внутренние reason codes.
- Если сведений пока нет, интерфейс объясняет пользу следующего шага: «Добавьте X — я смогу уточнить Y и рассчитать Z. Либо, после вашего разрешения, могу найти публичные источники».
- Кнопки главного пути вызывают существующие callbacks/API. Неподдерживаемые действия должны быть честно disabled, а не изображать работу.
- Admin остаётся отдельной технической консолью, но также должен соответствовать утверждённым admin-макетам и быть пригодным для демонстрации.

## 5. Обязательный процесс исправления UI

Сначала составь таблицу всех 14 состояний:

`макет → route/state → React/Streamlit component → реальные данные → callback/API → текущее визуальное расхождение`

Затем:

1. Сними baseline-скриншоты настоящего localhost UI при `1440×1000`.
2. Проверь каждый из 14 макетов, а не выборочные страницы.
3. Сначала выровняй общие design tokens, shell, сетку, типографику, размеры, поверхности, тени, кнопки и иконографику.
4. Затем исправь каждое состояние, сохраняя реальный backend workflow и честные empty/loading/error/blocked/approved состояния.
5. Графики и метрики должны выглядеть качественно, но строиться только из реальных подтверждённых или явно маркированных данных.
6. Через TDD защищай callbacks, API transitions, privacy projections и отсутствие fake demo state.
7. После каждой связной группы экранов запускай тесты и делай новые Playwright-скриншоты `1440×1000`.
8. Проведи независимый visual review и сравнение со всеми 14 PNG. Исправь Critical/Important расхождения.
9. Собери итоговый contact sheet или понятный набор `макет ↔ реализация`, чтобы владелец мог принять результат.

Playwright CLI разрешён для локальной автоматизации и скриншотов `127.0.0.1`. Это не разрешение на произвольные внешние web-вызовы.

Успешные unit-тесты, typecheck, lint или build сами по себе не означают визуальный PASS. Не объявляй UI принятым до новой явной оценки владельца. При этом после внутреннего visual review продолжай в этом же чате к функциональной логике — отдельный второй промт больше не нужен.

## 6. Существующий UI-WIP — сохранить и проверить

На момент передачи незакоммиченный WIP находится как минимум в следующих файлах:

- `frontend/founder/app/globals.css`
- `frontend/founder/app/globals.visual.test.ts`
- `frontend/founder/components/founder-shell.tsx`
- `frontend/founder/components/upload-entry.tsx`
- `frontend/founder/components/upload-entry.module.css`
- `frontend/founder/components/upload-entry-visual.test.ts`
- `frontend/founder/components/founder-workspace-controller.test.ts`
- `frontend/founder/components/founder-analysis-pages.tsx`
- `frontend/founder/components/founder-analysis-pages.module.css`
- `frontend/founder/components/founder-analysis-pages.test.ts`
- `frontend/founder/components/founder-strategy-pages.tsx`
- `frontend/founder/components/founder-strategy-pages.module.css`
- `frontend/founder/components/founder-strategy-pages.test.ts`
- `frontend/founder/components/founder-advisor-pages.tsx`
- `frontend/founder/components/founder-advisor-pages.module.css`
- `frontend/founder/components/founder-advisor-pages.test.ts`
- `src/due_diligence_agent/presentation/streamlit/components/audit.py`
- `tests/smoke/test_streamlit_admin_console.py`

На старом handoff были GREEN `npm test`, `npm run typecheck`, `npm run lint`, но это не подтверждает текущее состояние после последующих правок. Выполни fresh проверки. `npm run build` после последней UI-интеграции ещё не был доказан.

## 7. Как должен работать продукт

Пользователь загружает PDF бизнес-плана, презентацию, таблицы или заметки без обязательного prompt и без выбора отрасли. Система сама разбирает проект и на русском показывает:

- что за продукт и для кого он;
- понятные подтверждённые и рассчитываемые метрики;
- ключевые проблемы, риски и противоречия;
- рынок, TAM/SAM/SOM, прямых и косвенных конкурентов, заменители, потенциальных новых участников и вариант «ничего не делать»;
- что именно улучшить в продукте, монетизации, ICP, GTM, метриках и рисках;
- один следующий лучший вопрос, который сильнее всего улучшит анализ;
- четыре честных режима ответа: вручную, файлом, разрешённым публичным поиском или пропуском;
- немедленно обновлённый анализ и новую версию плана после ответа;
- приоритетный план действий на 7/30/60/90 дней;
- same-case JSON/HTML/PDF после Gate 4;
- Admin trace того же `case_id` с LangGraph/LangSmith, стоимостью, ошибками и lineage без приватного payload.

Не выдавай пользователю тупик «не хватает данных». Используй полезную формулировку:

> Если вы добавите X, я смогу уточнить Y и рассчитать Z. Либо, после вашего разрешения, могу найти публичные источники вместо вас.

При этом нельзя выдумывать метрики, факты, источники или уверенность. До подтверждения выводы маркируются как гипотеза, расчёт или «требует подтверждения».

## 8. Что уже сделано и не должно переделываться

- Queue 1–4 закрыты для deterministic frozen/offline scope.
- Tasks 0–7 Founder AI Advisor завершены и имеют отчёты/коммиты.
- Реализованы доменные схемы вопроса/ответа, consented public research boundary, deterministic improvement proposals, restart-safe advisor API facade и founder-safe Russian report presentation.
- Canonical offline Gates B/C/D/E должны оставаться deterministic, tracing-disabled и независимыми от сети.
- Не начинай R11/R12 и не переписывай доказанные Queue 1–4.

### Актуальный статус интернет-поиска

- Не повторяй устаревшую формулировку «настоящий интернет-поиск ещё не реализован».
- Реальный public web-search path уже реализован в `startup_web_research.py` и `startup_advisor_research_service.py`, подключён через explicit consent и покрыт offline producer-shaped/privacy/fallback тестами.
- Авторитетное доказательство: `.superpowers/sdd/2026-08-16-founder-ai-advisor-ux-completion/task-3-report.md`.
- Ещё не подтверждён только отдельный credentialed live-smoke с настоящим сетевым ответом. Не обещай доступность live-поиска без проверки конфигурации и provider health.
- Public research остаётся отдельным consent-gated advisor path. Canonical workflow и Gates B/C/D/E используют frozen/cached evidence и не зависят от сети.
- При отсутствии consent, ключа, бюджета, источников или при timeout/outage кейс продолжается с безопасным `deferred`/cached fallback, а не блокируется.

## 9. Главная функциональная задача после UI-аудита

Через TDD доведи настоящий сквозной пользовательский путь, а не отдельные функции и не статический demo state.

Сначала составь матрицу:

`экран → действие пользователя → API/graph transition → ожидаемый видимый результат → тест/доказательство`

Затем закрывай разрывы в порядке:

1. PDF upload → private case → primary profile.
2. Gate 2 → deep analysis.
3. Метрики/readiness → market/competitors/TAM-SAM-SOM → risks/contradictions/questions.
4. Один advisor question → manual/file/consented research/skip.
5. Updated analysis → six safe improvement proposals → accept/reject/version lineage.
6. Plan 7/30/60/90 → Gate 4 → same-case JSON/HTML/PDF.
7. Admin trace того же case с LangGraph, local audit, exporter health и LangSmith evidence.

Для каждого реального разрыва сначала producer-shaped RED test, затем минимальная реализация, затем GREEN. Не создавай параллельный fake frontend state, который обходит backend. Shared graph/ports/container/report меняет только один интегратор.

## 10. LangSmith, OpenAI и public research

- Offline Gates выполняются без сети и tracing export.
- После полного offline GREEN проверь только boolean наличия `LANGSMITH_API_KEY`, не печатая значение.
- При наличии ключа выполни один synthetic/frozen sanitized LangSmith smoke реального startup LangGraph workflow.
- В trace допустимы только безопасные `case_id/run_id/node/agent_role/duration/retry/error/gate/token-cost/report-lineage`.
- Запрещены raw PDF, document text, filenames, local paths, prompts, chain-of-thought, PII и secrets.
- Exporter outage не ломает workflow; local audit остаётся source of truth; Admin показывает exporter health.
- Без LangSmith evidence Queue 5 не закрывать. При отсутствии ключа оставить один честный credential blocker.
- После offline GREEN и только если есть `OPENAI_API_KEY` допускается максимум один bounded competitor-synthesis call с бюджетом `<= $0.25`, после Gate 2, только на sanitized StartupProfile и frozen competitor/source summaries, со structured output и single-call/timeout/budget guard.
- Live inference не называть live web research.
- Не выполнять live SEC/Yahoo/GDELT/news/web.
- Отдельный live Research Agent web smoke не запускать без нового явного разрешения владельца. Его functional consent/fallback boundary пока доказывается offline.

## 11. Обязательная проверка перед заявлением готовности

- frontend `test/typecheck/lint/build`;
- все 14 реальных desktop-состояний при `1440×1000` и screenshot comparison с макетами;
- настоящий PDF browser/API journey;
- fresh Gate B/C/D-A/D-B/E offline;
- полный backend pytest;
- Ruff;
- strict mypy;
- privacy, determinism, restart, failure matrix и report/trace lineage;
- sanitized LangSmith trace;
- bounded OpenAI competitor smoke при наличии ключа;
- demo script на 7–10 минут и one-page capstone map;
- независимый code/docs/visual/acceptance review без Critical/Important.

Не объявляй UI принятым, пока его повторно не одобрил владелец. Не объявляй Queue 5/Sellable Demo готовой, пока обязательные доказательства не собраны.

## 12. Git и защита пользовательских файлов

Сохраняй маленькие сфокусированные коммиты и используй только явный `git add -- <paths>`. Не использовать `git add -A`, `git reset`, `git checkout`, `git clean`, broad delete или переписывание чужого WIP.

Не удаляй, не откатывай, не перемещай, не перезаписывай и не добавляй в Git:

- `tests/evaluation/test_sellable_demo_freeze.py`
- `task15_r3_probe_app.py`
- `task15_r3_probe_data/`
- `.playwright-cli/`
- `.pytest-debug-readonly-store/`
- `artifacts/ui/m5-qa/`
- `c12ed5f`
- `.pytest-*`, `q2d-*`, `review-*` и другие runtime/temp artifacts
- существующие worktree и feature-ветки.

Перед каждым коммитом проверь `git diff --cached --name-only` и убедись, что staged только явные файлы текущей атомарной задачи.

## 13. Как начать работу в новом чате

После полного чтения и проверки Git дай владельцу короткую сводку:

1. какой точный HEAD и какой WIP найден;
2. что текущий UI зафиксирован как `owner_visual_acceptance = rejected`;
3. какие 14 route/state соответствуют 14 макетам;
4. какие три крупнейшие визуальные системные причины расхождения найдены;
5. какой первый RED-тест или visual assertion будет добавлен;
6. какой первый реальный end-to-end функциональный разрыв будет проверен после UI-аудита.

Затем продолжай автономно без ожидания подтверждения. Не трать время на новое обсуждение арт-направления: оно уже утверждено 14 макетами. Не маскируй визуальные расхождения зелёными тестами и не застревай только на дизайне — после реальной screen-by-screen интеграции продолжай тот же пользовательский workflow в этом же чате.

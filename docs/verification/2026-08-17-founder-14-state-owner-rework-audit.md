# Founder Intelligence — аудит 14 утверждённых desktop-состояний

> Historical checkpoint. Current visual status is superseded by `design-qa.md` and later Case Copilot/readable-UI verification. Do not interpret the status below as current.

Дата проверки: 2026-08-17
Ветка: `main`
Проверенный HEAD: `4c76a2a84da4a757f186478fb02ae39a37189779`
Статус владельца: `owner_visual_acceptance = rejected`

## Owner review checkpoint — 2026-08-17

- `01-start-dashboard`: визуально принят владельцем; не перерабатывать, кроме исправления доказанной общей регрессии.
- `02-data-room`: визуально принят владельцем; не перерабатывать, кроме исправления доказанной общей регрессии.
- `03-analysis-progress-gate2` … `14-ai-advisor-improved-plan`: требуют дальнейшей визуальной доработки.
- Последняя review-подборка содержит ровно 14 сравнений. Техническое разбиение contact sheet — `8 + 6`; прежние пользовательские подписи ссылок `01–07` и `08–14` были неточными.
- После сжатия контекста продолжать с экранов `03–14`; не запускать повторный полный аудит и не открывать заново принятые `01–02` без визуальной регрессии.

## Нормализация визуального сравнения

- Источник истины: `mockups/founder-intelligence-desktop/01-*.png` … `14-*.png`.
- Размер каждого исходного PNG: `1586×992`.
- Обязательный runtime viewport: `1440×1000`, desktop only.
- Исходный PNG для сравнения масштабируется пропорционально до `1440×901` и центрируется на холсте `1440×1000`; runtime-снимок сохраняется без масштабирования.
- Baseline-каталог: `artifacts/ui/founder-owner-rework-baseline-01a00ec7/`.
- Совмещённый baseline: `artifacts/ui/founder-owner-rework-baseline-01a00ec7/reference-vs-baseline-contact-sheet.png`.

## Карта состояний

Канонический demo-порядок: `01 → 02 → 03 → 04 → 11 → 12 → 13 → 14 → 05 → 06 → 07 → 08 → 09 → 10`.

| Макет | Route / state | Компонент | Реальные данные | Callback / API | Текущее расхождение |
| --- | --- | --- | --- | --- | --- |
| 01 Start dashboard | `/`, `dashboard` | `FounderShell` + `UploadEntry(dashboard)` | local file inventory; profile только после реального кейса | `onFilesSelected`, `onStartAnalysis` | Композиция близка по цвету, но до кейса всё ещё показывается каркас «Последний проект» и три псевдометрические ячейки; плотность нижнего ряда ниже референса. |
| 02 Data room | `/`, `data_room` | `FounderShell` + `UploadEntry(data-room)` | local inventory; backend ещё не вызван | `start()` → `POST /cases` → `POST /documents` | Правая колонка и upload-зона сжаты; privacy toggle только готовит локальный режим и сам не запускает consented research. |
| 03 Progress / Gate 2 | `/`, `progress_gate2` | `FounderAnalysisPages(progress_gate2)` | case, profile, Gate 2 preview | `POST /gate2/decision` | Высоты rail/agent rows меньше макета; видимые статусы агентов заданы локальным массивом, а не текущим trace/progress. |
| 04 Overview / readiness | `/`, `overview` | `FounderAnalysisPages(overview)` | profile + readiness/report projections | навигация в metrics/market/advisor/report | Сетка слишком равномерная и мелкая; часть blockers/suggestions — общий fallback, а не evidence-linked результат кейса. |
| 11 Advisor question | `/`, `advisor_next_question` | `FounderAdvisorPages(advisor_next_question)` | `GET /advisor/next-question` | открыть answer или `POST /advisor/answers` для skip | Runtime содержит выдуманные `5 компаний`, `$18 400`, `6–8 недель`, `45%–70%`; это Critical fake-demo-state. |
| 12 Advisor answer | `/`, `advisor_answer` | `FounderAdvisorPages(advisor_answer)` | next-question + accepted document ids | `POST /advisor/answers` с manual/file/consented research/skip | Четыре режима реально существуют; геометрия и визуальная иерархия заметно мельче референса, file mode зависит от уже принятого document id. |
| 13 Updated analysis | `/`, `advisor_updated_analysis` | `FounderAdvisorPages(advisor_updated_analysis)` | advisor answer + improvement response | retry / переход к improved plan | Показываются недоказанные `+8 п.п.`, `+5` и «высокий риск → средний»; canonical report/analysis фактически не пересчитывается ответом. |
| 14 Improved plan | `/`, `advisor_improved_plan` | `FounderAdvisorPages(advisor_improved_plan)` | improvement proposals + decision lineage | `POST /advisor/improvements/{id}/decision` | В реальном baseline получены 2, а не обязательные 6 proposals; присутствуют неподтверждённые high/confirmed claims, общий масштаб заметно ниже макета. |
| 05 Metrics / finance | `/`, `metrics` | `FounderAnalysisPages(metrics)` | readiness + report-derived charts | переход в report/data room | Honest empty-state сохранён, но карточки и chart-area примерно вдвое ниже референса; fallback MRR/ARR-каркас выглядит как dashboard-заготовка. |
| 06 Market / competitors | `/`, `market` | `FounderStrategyPages(market)` | GTM + report market/competitor sections | текущий market CTA только готовит research mode | Данные честно пустые, но competitor fallback может читаться как реальные категории; кольца, панели и recommendation strip слишком компактны. |
| 07 Risks / questions | `/`, `risks` | `FounderStrategyPages(risks)` | report risks/questions + readiness gaps | локальная навигация; Gate 3 exclusions не доступны | Risk rows и contradiction card существенно ниже/плоше референса; вопросы fallback могут читаться как реальные выводы. |
| 08 Action plan | `/`, `action_plan` | `FounderStrategyPages(action_plan)` | GTM `7/30/60/90` + report action plan | `POST /gate3/decision` с пустыми exclusions | Реальный Gate 3 есть, но пользователь не может решить конкретные противоречия; proposal cards и timeline слишком редкие. |
| 09 Report center / Gate 4 | `/`, `report_center` | `FounderStrategyPages(report_center)` | validated report tuple + JSON/HTML/PDF URLs | `POST /gate4/decision` → artifacts | Same-case report готов, но Gate 4 реализован вне LangGraph interrupt/resume; визуально отсутствует главный cover-anchor макета и reject path. |
| 10 Admin observability | `:8501/` (`/admin` redirect) | Streamlit `pages/admin.py` + `components/audit.py` | local audit + optional sanitized LangSmith exporter | case/run selection | Реальный graph/tools/cost/lineage есть; Streamlit-полотно длиннее viewport, узлы и KPI мельче референса, Critic/Arbiter не представлены отдельными graph nodes. |

## Системные причины визуального drift

1. Shell, sidebar, gutters, card heights и вертикальный ритм не нормализованы от `1586×992` к `1440×1000` как единая геометрическая система.
2. Типографическая шкала и spacing раздроблены между `globals.css` и тремя крупными CSS Modules; одинаковые роли имеют разные размеры и плотность.
3. Glass/depth, icon bubbles, charts, timelines и emphasized panels реализованы локальными вариантами вместо общего повторяемого visual vocabulary.

## Первый функциональный разрыв после визуального аудита

Browser journey `PDF upload → private case → Gate 2` существует и в baseline создал case `29be4c72-df15-4049-b923-fcb2b88f964a`, но текущий smoke harness должен доказать, что case создан именно DOM-upload действием, а не API pre-seed. Следующий разрыв — advisor answer не запускает canonical graph/report recalculation, а Gate 4 не является LangGraph interrupt/resume checkpoint.

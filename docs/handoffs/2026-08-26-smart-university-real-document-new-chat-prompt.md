# Smart University real-document acceptance — new chat prompt

Copy this whole file into a fresh Codex chat, or use the already-created continuation task.

```text
Продолжай Capstone N3 в текущем рабочем состоянии и доведи реальный Smart University кейс до полностью проверяемого пользовательского сценария. Это implementation/acceptance задача, не только анализ.

Рабочая папка текущего состояния:
C:\Users\Akana\.codex\worktrees\6e2b\Capstone N3

Ветка:
codex/case-copilot-docker

Сначала полностью прочитай, в указанном порядке:

1. docs/handoffs/2026-08-26-smart-university-real-document-new-chat-prompt.md
2. docs/superpowers/plans/2026-08-26-smart-university-real-document-acceptance.md
3. docs/handoffs/2026-08-22-case-copilot-v1-new-chat-prompt.md
4. docs/superpowers/specs/2026-08-22-founder-case-copilot-v1-design.md
5. docs/superpowers/specs/2026-08-22-founder-case-copilot-scenario-metrics-addendum.md
6. docs/superpowers/plans/2026-08-22-founder-case-copilot-scenario-launch.md
7. docs/handoffs/2026-08-25-case-copilot-live-public-search-docker-handoff.md
8. frontend/founder/AGENTS.md перед frontend-правками.

Используй:

- superpowers:systematic-debugging для текущих ошибок;
- superpowers:test-driven-development для каждого исправления;
- superpowers:subagent-driven-development для исполнения нового acceptance-плана task-by-task;
- отдельные spec-compliance и code-quality review gates после каждой implementation task;
- superpowers:verification-before-completion перед финальным заявлением.

Не повторяй уже принятые Case Copilot Tasks 1-11 и Docker Tasks 0-4. Текущая задача — реальный документ, recovery UX, публичный поиск и полный acceptance run.

Реальный документ владельца:
C:\Users\Akana\OneDrive\Рабочий стол\Smart_University_Full_Business_Plan_2026.pdf

PDF уже проверен в предыдущем чате:

- 29 страниц;
- 833 028 байт;
- не зашифрован;
- текст извлекается, визуально страницы и таблицы читаются;
- диагностический текст: tmp/pdfs/smart-university-review/full-text.txt;
- contact sheets: tmp/pdfs/smart-university-review/pages-01-10.png, pages-11-20.png, pages-21-29.png.

Главный уже доказанный дефект:

- Docker web/API/admin здоровы на 3000/8180/8501;
- frontend создаёт кейс успешно: POST /api/v1/startup/cases -> 201;
- загрузка реального PDF падает: POST /api/v1/startup/cases/{case_id}/documents -> 409;
- точный founder-safe body:
  {"code":"startup_document_intelligence_input_invalid","message":"startup_document_intelligence_input_invalid"}
- свежая ручная репродукция: case_id 404e650c-7d8e-49ea-834b-264b18d0b161;
- в Docker-логах та же последовательность ещё для case ids 00a9afd4-3236-4d6a-8267-4c0f9b4ef288, 5bb4c69a-7ece-4173-9dc8-f8194d586d2d и c42c7975-813a-4488-a2fa-e4e3746f60d4.

Граница ошибки в коде:

- src/due_diligence_agent/workflows/startup/ports.py, StartupDocumentIntelligenceWorkflowAdapter.analyze;
- StartupDocumentIntelligenceService.analyze выбрасывает ValueError;
- adapter превращает любую такую ошибку в startup_document_intelligence_input_invalid, скрывая точную нарушенную предпосылку от текущей диагностики.

Первое действие нового чата:

1. Запустить RED из Task A нового плана:
   py -3.13 -B -m pytest tests/api/test_startup_smart_university_real_document.py -q -p no:cacheprovider
2. Если теста ещё нет, сначала создать его так, чтобы он воспроизводил именно 409 startup_document_intelligence_input_invalid на реальном PDF или на минимизированном документе с тем же структурным триггером.
3. Найти исходный ValueError внутри StartupDocumentIntelligenceService.analyze.
4. Исправить минимальную причину, не подавлять исключение и не хардкодить Smart University.

Второй обязательный дефект:

- после upload failure UI выглядит как зависший шаг 2 с пустым профилем;
- интерфейс не должен переходить в стабильный Profile/Gate 2 state после отклонённого документа;
- после принятого upload UI должен хранить receipt файла, показывать этап обработки/loader и не возвращаться к «Ожидает материалы»;
- disabled Gate 2 CTA обязан объяснять точную причину и давать рабочий repair action;
- no-action Case Copilot state не должен показывать бесполезный disabled «Сохранить ответ».

Третий обязательный дефект:

- при отмеченном consent пользователь видел «Публичный поиск не удалось запустить. Проверьте согласие...»;
- разнести deferred/provider-unconfigured/stale-plan/provider-failed/invalid-contract/consent-missing состояния;
- deterministic_offline proof выполнить первым;
- configured-live использовать только через D:\Agents\Projects\Capstone N3\.env, не печатая ключи;
- public research никогда не заполняет private revenue/MRR/cash/burn/customer/contracts как source_fact.

Ожидаемая интерпретация Smart University:

- stage: existing first_sales / pre-scale, не idea; новый enum не добавляй без доказанной необходимости;
- working product с техническими evidence claims, но коммерческая traction ещё не подтверждена;
- platform и housing vertical анализировать раздельно;
- 2027-2031 numbers — forecasts/model outputs, не actual performance;
- 35.2M KZT platform round и отдельный 8M KZT housing pilot не смешивать;
- PDF-ссылки S1-S17 без URL считать source stubs, требующими верификации.

Ключевые выводы из документа, которые acceptance run должен увидеть:

- платформа: grant navigator 5 632 cutoffs / 87 universities, KBTU/KazNU/NU data, 652 RAG chunks, RU/KK/EN advisor, Docker/admin, 71 hermetic tests;
- commercial gaps: auth/roles, billing, receipts, CRM, production data SLA, cohorts/anti-fraud, confirmed CAC/churn/renewal/school ROI;
- pricing: 300k, 750k + 4k/lead, 1.5M + 3k/lead, 2.5M + 2.5k/lead; early pilot 300-500k for 6-9 months;
- assumptions: gross margin 85%, CAC 450k, churn 20%, accepted lead >=60%, LTV/CAC >=3;
- financial forecast: revenue 8.4M -> 342.5M KZT and EBITDA -17.9M -> 166.1M for 2027-2031;
- rating: minimum 20 verified students, Bayesian prior 30, 12-month window, paid influence 0%;
- housing: asset-light management first; current master lease/purchase calculations include no-go conditions;
- 90-day objective: 3 paid pilots/payments, full lead cycle, measured willingness to pay and conversion of assumptions into facts.

Сохраняй текущий dirty WIP:

- не делать reset, clean, checkout, revert или stash;
- не удалять runtime/test/browser artifacts;
- user-owned tracked dirty files frontend/founder/next-env.d.ts и frontend/founder/tsconfig.json не перетирать;
- local commits разрешены после GREEN + review gates;
- не push/merge/deploy/publish без отдельного запроса.

Текущие локальные commits, которые нельзя потерять:

- 02166a5d Clarify Case Copilot public research state
- fb68c8ac Document Case Copilot UI unblock
- 85a62519 Use current Case Copilot revision for saves
- 8d2683c0 Document Case Copilot save revision fix

Docker сейчас запущен:

- http://127.0.0.1:3000/
- http://127.0.0.1:8180/docs
- http://127.0.0.1:8501/

Не ограничивайся unit tests. После исправлений прогоняй этот реальный PDF через один и тот же persisted case: upload -> profile -> questions -> founder input/unknown -> safe public research -> scenarios -> metrics/risks/actions -> GTM launch pack -> restart proof. В финале дай владельцу понятную русскую пошаговую инструкцию работы с продуктом и точный список того, что документ подтвердил, что осталось предположением, что найдено публичным поиском и что требует реальной проверки.
```

## Safe-pause state

- На этом диагностическом проходе production code не изменялся.
- Добавлены только этот handoff и дополнительный acceptance plan.
- Docker оставлен запущенным; данные volume не удалялись.
- Все диагностические subagents работали read-only.

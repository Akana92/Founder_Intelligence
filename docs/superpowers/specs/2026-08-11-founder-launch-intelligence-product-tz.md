# Founder Launch Intelligence

## Полное описание идеи и техническое задание

| Поле | Значение |
|---|---|
| Проект | Capstone N3 |
| Направление | Vertical AI & Industry Solutions — FinTech, Startup Intelligence и инвестиционная аналитика |
| Рабочее название продукта | Founder Launch Intelligence |
| Основной режим | Startup Launch Analyzer |
| Вторичный режим | Public Company & Comparable Analysis |
| Основной пользователь | Основатель стартапа, который хочет проверить идею и подготовить продукт к выходу на рынок |
| Статус документа | Версия 1.2: выбран delivery profile B и утверждён универсальный двухуровневый анализ без выбора отрасли пользователем |
| Дата | 2026-08-11 |
| Архитектурная база | Modular Monolith, Ports and Adapters, LangGraph, Evidence Ledger |
| Профиль первой поставки | B — Sales-Ready Hybrid: отдельный product-grade Founder frontend, Python application/API backend и временно допустимый Streamlit Admin Console |
| Пользовательский вход | Загрузка одного документа или набора документов без выбора отрасли, шаблона проекта или заранее подготовленного кейса |
| Визуальное направление | Analyst Terminal, адаптированный для нефинансового пользователя |

## 1. Статус и место документа в проекте

Этот документ фиксирует обновлённое продуктовое ядро Capstone N3: основным продуктом становится анализатор стартапа для основателя, а анализ публичных компаний становится вторичным модулем для comparables, рыночного контекста и демонстрации работы с SEC, рыночными данными и новостями.

Документ заменяет прежнюю расстановку продуктовых приоритетов, но не отменяет уже утверждённые технические принципы и готовую реализацию Stage 1A. Если положения настоящего документа и спецификации Investment Due Diligence Agent от 2026-08-09 различаются, приоритет имеют:

1. Настоящий документ — для продуктового позиционирования, состава Founder Workspace, состава Admin Console, продаваемого демо и порядка дальнейшей поставки.
2. [Спецификация от 2026-08-09](2026-08-09-investment-due-diligence-agent-design.md) — для общих архитектурных, privacy, evidence, tracing, calculation и report contracts, если они не изменены здесь явно.
3. Фактически работающий Stage 1A — для уже реализованных интерфейсов, тестов и технических ограничений.
4. Отдельные implementation plans — для точных файлов, интерфейсов и порядка изменения кода после утверждения ТЗ.

Решением владельца продукта от 2026-08-11 выбран delivery profile B — Sales-Ready Hybrid. Это решение фиксирует границу поставки: Founder Workspace создаётся как отдельная коммерческая browser-поверхность поверх существующего Python-ядра, а Admin Console на первой стадии может переиспользовать Streamlit. Остальные параметры Decision Gate 0 остаются открытыми и перечислены в разделе 33.

Delivery profiles B и C не являются разными видами анализа. В обоих случаях пользователь должен получить одинаковый первичный и глубинный анализ. Различие касается только способа разработки, развёртывания и эксплуатационной зрелости продукта: B быстрее создаёт продаваемую пользовательскую поверхность поверх готового Python core, а C дополнительно требует полноценной multi-user, security и operations платформы.

Состояние продукта на дату документа:

- Прямо проверяемый локальный Gate B artifact для Public Company Stage 1A и dataset `public_us_frozen_v1` имеет `gate_b_passed=true`, создан 2026-08-11 для commit `f509c90b26b487238ac2f098c32711845b32e913` и содержит JSON, HTML, PDF и audit paths. Предыдущий execution handoff также сообщал 388 успешных тестов и 92 процента покрытия, но отдельный pytest/coverage artifact с этими двумя числами в ходе подготовки ТЗ не найден; поэтому они считаются историческим ориентиром до обязательного повторного прогона в R1, а не подтверждённым текущим KPI.
- Канонический JSON, HTML и PDF отчёт, Evidence Ledger, детерминированные метрики, LangGraph, bounded Reflexion, HITL, tracing и privacy boundary уже имеют рабочую основу.
- Текущий браузерный интерфейс является инженерным Streamlit-прототипом Public Company Mode и не соответствует целевому продаваемому Founder-first UX.
- Startup Data Room, Startup Workflow, адаптивные вопросы, metric packs и Launch Readiness ещё не должны считаться реализованными только потому, что они описаны в плане.

Локальный источник Gate B evidence: `.worktrees/stage1a-public-demo/output/gate-b/public_us_frozen_v1/eval-result.json`. При переносе проекта этот generated artifact может отсутствовать и должен быть пересоздан командой Gate B.

### 1.1 Канонические термины

| Термин | Значение в этом проекте |
|---|---|
| Founder Launch Intelligence | Название продукта целиком |
| Startup Launch Analyzer | Основной пользовательский сценарий: загрузка материалов, автоматический анализ и отчёт |
| Первичный анализ | Автоматический быстрый результат после загрузки: профиль, сильные стороны, слабые места, пробелы, начальные риски и применимые метрики |
| Глубинный анализ | Продолжение того же кейса: внешнее исследование, детальные метрики, конкуренты, сценарии, противоречия, адаптивные вопросы, план действий и полный отчёт |
| Public Company & Comparable Analysis | Вторичный режим для SEC, публичных компаний, comparables и рыночного контекста |
| Founder Workspace | Пользовательский интерфейс основателя без технической операционной информации |
| Admin Console | Отдельный административный интерфейс tracing, privacy, evals, budgets и integrity |
| Startup Workflow / Public Workflow | Технические LangGraph-процессы, не названия пользовательских продуктов |

### 1.2 Типы gates

| Тип | Обозначение | Назначение |
|---|---|---|
| Product Decision Gate | Decision Gate 0 | Выбор владельцем delivery profile и границ первой поставки |
| Delivery Stage | R0–R12 | Последовательная стадия roadmap с собственным результатом и stop condition |
| Evaluation Gate | Gate A–E | Автоматизированная проверка качества foundation или продуктовой вертикали |
| Runtime/HITL Gate | Gate 1–4 | Решение человека внутри конкретного анализа: scope, egress, contradiction, report freeze |
| Stage Acceptance Review | UX Shell Review, Evidence Gate, Metric Gate и аналогичные | Локальная проверка результата конкретной delivery stage; не заменяет Gate A–E |

## 2. Резюме продуктовой идеи

Founder Launch Intelligence — это не чат с искусственным интеллектом и не генератор красивого текста о стартапе. Это управляемая система подготовки продукта к выходу на рынок.

Пользователь загружает поддерживаемые в первой версии материалы: презентацию или описание идеи в PDF/DOCX, финансовую модель и таблицы в XLSX/CSV, изображения либо безопасный ZIP с такими файлами. Система самостоятельно определяет, что за бизнес находится перед ней, какие утверждения уже подтверждены, какие данные противоречат друг другу, какие метрики применимы к этой бизнес-модели и какие критические вопросы ещё не были заданы. Неподдерживаемый или небезопасный файл учитывается в inventory, получает понятный статус и при необходимости помещается в quarantine, но не объявляется полноценно проанализированным.

Первый результат система выдаёт без требования написать правильный промпт и без выбора отрасли. Она сама определяет одну или несколько гипотез бизнес-модели и сразу строит первичный анализ. После этого в том же кейсе доступен глубинный анализ: система показывает три наиболее важных вопроса, объясняет незнакомые метрики, проводит разрешённое внешнее исследование, предлагает допустимые виды доказательств и превращает найденные проблемы в план экспериментов и действий.

Основной результат для пользователя:

- понятный профиль стартапа;
- сильные стороны и рыночные преимущества;
- слабые места и критические блокеры;
- прямые, косвенные и потенциальные конкуренты;
- применимые бизнес-метрики и состояние данных для их расчёта;
- evidence-backed оценка готовности к рынку;
- конкретный план на 7, 30, 60 и 90 дней;
- скачиваемый PDF с графиками, таблицами, источниками и ограничениями анализа.

## 3. Проблема рынка

У основателя обычно нет единого структурированного data room и полного набора знаний в продуктовой аналитике, финансах, исследованиях рынка и инвестиционной подготовке. Материалы распределены между презентациями, таблицами, заметками и гипотезами. В результате основатель:

- не знает, какие данные критичны именно для его бизнес-модели;
- не знает, какие вопросы задать ИИ или консультанту;
- может преждевременно считать непроверенную гипотезу фактом;
- не замечает расхождения между pitch deck, финансовой моделью и фактическими данными;
- выбирает метрики по популярности, а не по применимости;
- получает общий совет без доказательств, приоритета и плана проверки;
- тратит время и деньги на ручной анализ нескольких специалистов.

Обычный AI-чат способен помочь только после того, как пользователь сформулировал правильную задачу и передал правильный контекст. Founder Launch Intelligence содержит саму методологию проверки и поэтому самостоятельно создаёт план анализа, управляет доказательствами, считает метрики и выявляет пропущенные вопросы.

## 4. Цели продукта

### 4.1 Бизнес-цели

1. Дать основателю полезный первичный диагноз даже при неполном наборе документов.
2. Сократить путь от хаотичных материалов до структурированного плана выхода на рынок.
3. Создать демонстрационный продукт, ценность которого понятна без технического объяснения AI-стека.
4. Сформировать доверие через доказательства, расчёты, ограничения и воспроизводимость.
5. Создать основу для дальнейшей продажи продукта основателям, акселераторам, консультантам и инвестиционным командам.

### 4.2 Пользовательские цели

Основатель должен понять:

- что именно он строит и для кого;
- насколько подтверждена проблема и готовность платить;
- что является сильной стороной идеи;
- что препятствует выходу на рынок;
- какие данные и метрики необходимо начать собирать;
- какие конкуренты и альтернативы уже решают ту же задачу;
- какие эксперименты дадут наиболее полезные доказательства;
- что следует сделать в ближайшие 7, 30, 60 и 90 дней.

### 4.3 Технические цели

- каждый критический вывод связан с источником, расчётом, противоречием или явной нехваткой данных;
- арифметика и канонические метрики выполняются детерминированным Python-кодом;
- workflow имеет план, конечные бюджеты, checkpoint recovery и понятные stop conditions;
- система ищет контрдоказательства и противоречия не более чем в двух Reflexion-итерациях;
- raw startup documents остаются локальными по умолчанию;
- tracing, evaluation и privacy являются обязательной частью продукта;
- один неизменяемый Report JSON является источником для HTML и PDF;
- отказ некритичного источника не уничтожает весь анализ.

## 5. Целевая аудитория и пользовательские задачи

### 5.1 Основной пользователь

Основатель или сооснователь стартапа на стадии идеи, pre-seed или seed, который хочет провести полную проверку предполагаемого продукта и может не владеть финансовой или продуктовой терминологией.

Его основная задача:

> Загрузить то, что уже есть, и получить честный ответ: что подтверждено, чего не хватает, что опасно и что делать дальше.

### 5.2 Вторичные пользователи

- продуктовый консультант — для ускорения диагностики клиентского проекта;
- акселератор или инкубатор — для единообразной первичной оценки участников;
- аналитик или инвестор — для быстрого обзора evidence quality и ключевых рисков;
- член команды стартапа — для подготовки метрик, data room и GTM-плана.

### 5.3 Административный пользователь

Оператор или технический владелец контролирует состояние workflow, tracing, privacy, стоимость, качество источников, evaluation gates и целостность отчётов. Эти функции не должны перегружать интерфейс основателя.

## 6. Продуктовые контуры и режимы

### 6.1 Первичный анализ — обязательный первый результат

Пользователь загружает один документ или смешанный набор материалов. Система без отраслевого селектора проверяет файлы, определяет предполагаемую бизнес-модель и стадию, строит первичный профиль, выделяет сильные стороны, слабые места, критические пробелы, начальные риски, claims и подходящий набор метрик. Если данных мало, система всё равно выдаёт полезный результат и явно показывает ограничения.

Первичный анализ не является заранее записанным demo-case или сокращённым рекламным экраном. Во время демонстрации используется тот же workflow, которым затем будет пользоваться реальный основатель.

### 6.2 Глубинный анализ — продолжение того же кейса

После первичного результата система углубляет проверку: исследует рынок и конкурентов, рассчитывает доступные unit economics и финансовые сценарии, ищет контрдоказательства и противоречия, уточняет readiness, формирует launch thesis, counter-thesis и план 7/30/60/90. Когда для существенного вывода не хватает данных, система выбирает не более трёх наиболее важных вопросов и предлагает пользователю ответ, диапазон, файл или альтернативное доказательство. Глубинный анализ не создаёт новый проект и не требует повторной загрузки документов.

### 6.3 Public Company & Comparable Analysis — вторичный режим

Используется для:

- анализа публичной компании по ticker;
- исследования публичных конкурентов стартапа;
- comparable analysis;
- демонстрации SEC filings, market data, news и sentiment;
- финансовых benchmark-сигналов, когда сопоставимость обоснована.

Этот режим не должен быть главным пунктом стартового экрана и не должен конкурировать с Startup Launch Analyzer в продуктовой истории.

### 6.4 Admin Console — отдельный технический контур

Admin Console показывает, что продукт является контролируемой AI-системой, а не скрытым prompt wrapper. В нём размещаются graph tracing, audit, evaluation, privacy, budgets, source health и report integrity.

## 7. Чем продукт отличается от обычного AI-чата

| Обычный AI-чат | Founder Launch Intelligence |
|---|---|
| Ждёт правильный вопрос | Сам создаёт план обязательных проверок |
| Получает только выбранный пользователем контекст | Инвентаризирует весь разрешённый data room |
| Может не заметить отсутствующую метрику | Выбирает metric pack по бизнес-модели и стадии |
| Может выполнять арифметику непоследовательно | Использует версионированный детерминированный Metric Engine |
| Может смешать факт и интерпретацию | Маркирует источник, расчёт, вывод и нехватку данных отдельно |
| Может принять противоречивые числа | Сохраняет конфликт и запускает отдельную проверку |
| Даёт общий совет | Привязывает действие к риску, метрике и ожидаемому доказательству |
| Забывает ход анализа | Хранит case state, checkpoints, approvals и report snapshots |
| Не доказывает качество работы | Имеет eval datasets, quality gates и tracing |
| Требует от пользователя финансовых знаний | Объясняет метрику, формулу, входы и способ начать измерение |

### 7.1 Обязательные признаки, что продукт не превратился в чат

Продукт считается соответствующим замыслу только если:

1. Пользователь может начать полноценный анализ без написания промпта.
2. Система сама определяет предполагаемую бизнес-модель, стадию, ICP, рынок и пробелы.
3. Система самостоятельно предлагает применимый metric pack.
4. Каждый критический совет связан с evidence, calculation, contradiction или insufficient data.
5. При нехватке данных система выдаёт адаптивный вопрос или план измерения, а не выдумывает значение.
6. Чат, если он появится, остаётся дополнительным способом исследовать уже построенный кейс, а не главным продуктовым workflow.

## 8. Соответствие исходному capstone-заданию

| Критерий или технология | Реализация в продукте | Что должно быть видно на демо |
|---|---|---|
| Загрузка PDF | Универсальный Data Room с PDF, DOCX, XLSX, CSV, изображениями и ZIP | Загрузка собственного mixed-format набора документов |
| SEC Filings | Первичный источник для публичных comparables | Public comparable с filing evidence |
| Yahoo Finance | Research-only market adapter, не source of record | Рыночный snapshot с маркировкой источника |
| Последние новости | Web, RSS или GDELT research с датой среза и ссылками | News signals и ограничения coverage |
| Python Code Interpreter | Exploratory analysis разрешённых данных с обязательной локальной перепроверкой | Видимый calculation provenance |
| Детерминированный Python | Канонические unit economics и финансовые метрики | Формула, входные факты и результат |
| Plan-and-Execute | Планирование, сбор, анализ, проверка и синтез в LangGraph | Понятный progress и Agent Graph |
| Reflexion | Поиск противоречий и контрдоказательств, максимум две итерации | Найденный planted conflict |
| Multi-agent консилиум | Специализированные bounded nodes/roles с общим Evidence Ledger | Роли Product, Market, Financial, GTM, Risk, Critic и Arbiter |
| Sentiment | Вторичный сигнал по доступным новостям и публичным упоминаниям | Polarity с источниками и предупреждением |
| Интерактивные графики | Plotly в браузере, Matplotlib для статического fallback | Readiness, metrics, risks и trends |
| PDF с таблицами | Rendering канонического Report Snapshot | Скачиваемый draft/final PDF |
| Tracing | Sanitized LangSmith, OpenTelemetry и durable local audit | Отдельная Admin Console |
| Evaluation | Frozen datasets, deterministic evaluators и regression gates | Страница качества с Gate A–E |

## 9. Сквозной пользовательский сценарий

| Шаг | Действие пользователя | Действие системы | Результат |
|---|---|---|---|
| 1 | Создаёт анализ | Создаёт универсальный кейс без выбора отрасли или шаблона проекта | Понятный старт без промпта и классификатора |
| 2 | Загружает документы | Проверяет безопасность, типы, лимиты и inventory | Карта принятых, проблемных и отсутствующих материалов |
| 3 | Подтверждает scope | Локально разбирает текст, таблицы и изображения | Нормализованные artifacts и locators |
| 4 | При необходимости подтверждает privacy policy | Классифицирует и редактирует чувствительные данные | Разрешённый или local-only AI-путь |
| 5 | Наблюдает первичный анализ | Определяет модель, профиль, claims, базовые metrics, strengths, weaknesses и gaps | Первый полезный диагноз |
| 6 | Открывает глубинный анализ | Исследует рынок, конкурентов, риски, сценарии и контрдоказательства | Полная картина готовности к рынку |
| 7 | Отвечает на три приоритетных вопроса или пропускает их | Пересчитывает зависимые ветки, metrics и confidence | Уточнённый анализ без длинной анкеты |
| 8 | Разрешает критические противоречия или оставляет их открытыми | Сохраняет решение и пересчитывает зависимости | Честный статус claims и рисков |
| 9 | Просматривает план действий | Связывает действия с рисками, метриками и доказательствами | План 7/30/60/90 |
| 10 | Утверждает snapshot | Замораживает Report JSON и строит HTML/PDF | Воспроизводимый отчёт |

## 10. Founder Workspace

### 10.1 New Analysis

Стартовый экран должен объяснить ценность одной фразой и позволить:

- загрузить собственные материалы;
- продолжить существующий кейс;
- вторично перейти к Public Company Comparable Analysis.

Пустое состояние обязано объяснять, что неполный набор данных допустим. На стартовом экране нет выбора SaaS, marketplace, e-commerce, fintech или другого типа проекта: бизнес-модель определяется по документам. Пользователь не должен видеть технические настройки модели, tracing или fixture adapters.

### 10.2 Data Room

Показывает:

- принятые файлы;
- распознанный тип документа;
- parsing confidence;
- покрываемые области бизнеса;
- quarantined, unsupported, low-confidence и missing items;
- sensitivity category без раскрытия секретных значений;
- связь производного содержимого с исходным файлом.

### 10.3 Первичный и глубинный анализ

Первичный анализ запускается автоматически после безопасного разбора документов. Founder-facing progress отражает понятные этапы:

1. Чтение документов.
2. Построение профиля стартапа.
3. Проверка утверждений и чисел.
4. Выбор метрик.
5. Исследование рынка и конкурентов.
6. Поиск рисков и противоречий.
7. Подготовка рекомендаций.

После первичного результата пользователь остаётся в том же кейсе и переходит к глубинному анализу. Интерфейс сохраняет первичный snapshot для сравнения и показывает, какие выводы были подтверждены, изменены или отклонены после внешнего исследования, расчётов, вопросов и Reflexion.

Вместо внутренних ошибок показывается бизнес-понятное partial состояние: какая часть первичного или глубинного анализа недоступна, почему и как это влияет на результат.

### 10.4 Startup Profile

Показывает:

- one-liner продукта;
- проблему и решение;
- ICP и пользователей;
- бизнес-модель;
- стадию;
- географию;
- pricing model;
- traction signals;
- основные assumptions;
- уровень уверенности и источник каждого поля.

Пользователь может исправить неверно определённую модель или assumption. Исправление создаёт новую версию данных и пересчитывает зависимые результаты.

### 10.5 Launch Readiness Dashboard

Содержит:

- Launch Readiness Score;
- confidence и evidence coverage отдельно от score;
- Market Attractiveness;
- Problem Validation;
- Competitive Position;
- Business Model Clarity;
- Unit Economics;
- GTM Readiness;
- Execution Risk;
- Evidence Quality;
- Top strengths;
- Top blockers;
- Next best actions.

Score не является инвестиционной рекомендацией или объективной стоимостью бизнеса. Интерфейс обязан показывать методологию, версию модели оценки и влияние отсутствующих данных.

### 10.6 Market & Competitors

Показывает:

- прямых конкурентов;
- косвенных конкурентов;
- substitute solutions;
- альтернативу do nothing;
- публичные comparables;
- pricing и positioning signals;
- рыночные тренды;
- новости и sentiment;
- чему основатель может научиться у каждого конкурента;
- дату, источник и confidence каждого внешнего сигнала.

### 10.7 Product Validation

Анализирует:

- ясность проблемы;
- точность ICP;
- выраженность боли;
- срочность;
- willingness to pay;
- существующее поведение клиента;
- friction, switching cost и adoption risk;
- наличие интервью, LOI, пилотов, оплат или других доказательств.

### 10.8 Business Model & Metrics

Показывает применимые метрики, их смысл, формулу, входные данные, рассчитанное значение, confidence, период, предупреждения и следующий способ измерения. Нерассчитываемая метрика не должна отображаться как ноль.

### 10.9 Risks & Gaps

Риски группируются по рынку, клиенту, продукту, финансам, GTM, конкуренции, regulation signals, качеству данных и исполнению. Каждый риск содержит severity, likelihood, evidence strength, объяснение, mitigation и рекомендуемый эксперимент.

### 10.10 Evidence & Contradictions

Экран показывает claim–evidence matrix со статусами:

- Verified;
- Partially verified;
- Contradicted;
- Unsupported;
- Insufficient data;
- Needs founder answer.

Сначала показывается краткое объяснение, затем раскрываемая строка, затем locator документа, страницы, таблицы или ячейки.

### 10.11 Adaptive Questions

Пользователь видит не более трёх приоритетных вопросов одновременно. Для каждого вопроса показываются:

- зачем он задаётся;
- какой риск, вывод или метрику изменит ответ;
- какие форматы ответа допустимы;
- какой файл или иной тип доказательства подходит;
- что произойдёт при пропуске.

### 10.12 Action Plan

План включает:

- immediate blockers;
- действия на 7, 30, 60 и 90 дней;
- validation experiments;
- метрики, которые необходимо начать отслеживать;
- документы, которые нужно подготовить;
- investor/data-room readiness checklist.

Каждое действие связывается с ожидаемым impact, effort, владельцем, сроком, риском, метрикой и ожидаемым доказательством.

### 10.13 Report

Пользователь видит browser preview, статус draft/final и скачивание JSON, HTML и PDF. Draft должен содержать явную маркировку нерешённых противоречий и отсутствующих approvals.

## 11. Admin Console

### 11.1 System Overview

- активные и завершённые кейсы;
- blocked и failed runs;
- текущие Gate A–E;
- tracing и audit health;
- source health;
- средняя latency;
- token и cost summary;
- privacy alerts.

### 11.2 Agent Graph

Показывает план и фактически выполненные узлы, status, duration, retry count, fallback, input/output artifact IDs, checkpoint и sanitized trace link. Raw document text не показывается.

### 11.3 Trace Explorer

Объединяет durable local audit, OpenTelemetry spans и разрешённые LangSmith trace IDs. Если внешний tracing недоступен, локальный audit продолжает работать и считается источником воспроизводимости.

### 11.4 Evaluation Gates

- Gate A — shared foundation, privacy и tracing contracts;
- Gate B — Public Company vertical;
- Gate C — Startup ingest и privacy;
- Gate D — Startup vertical;
- Gate E — combined regression.

Для каждого gate показываются статус, дата, dataset, commit/build, hashes, основные метрики и причина блокировки.

### 11.5 Privacy & Egress

Показывает категории локальных данных, redaction status, approved disclosure scope, denied calls и privacy leak count. Admin Console не должен становиться способом просмотра raw confidential prompts.

### 11.6 Sources & Cache

Показывает источники, as-of, свежесть cache, failed adapters, license/usage flags, live/fixture mode и unsupported coverage.

### 11.7 Cost, Tokens & Latency

Показывает стоимость и длительность по кейсу, модели, узлу и fallback, а также budget stops и медленные этапы.

### 11.8 Report Integrity

Показывает snapshot ID, source hashes, calculation versions, approval binding, renderer, report artifacts и воспроизводимость.

## 12. Универсальный Data Room и безопасность файлов

Поддерживаемые типы первой полной версии:

- PDF;
- DOCX;
- XLSX;
- CSV;
- PNG и JPEG;
- ZIP только с разрешёнными типами.

Безопасные значения по умолчанию:

- не более 100 файлов на кейс;
- не более 250 MB на отдельный файл;
- не более 1 GB суммарного распакованного объёма;
- глубина вложенных архивов не более двух;
- decompression ratio не более 100 к 1;
- content sniffing вместо доверия расширению;
- защита от zip-slip, archive bombs и unsafe paths;
- подозрительный файл помещается в quarantine, а остальные продолжают обработку.

Parsing, OCR, redaction и local embeddings работают без скрытых runtime downloads. Низкая уверенность извлечения не превращается в подтверждённый факт без corroboration или HITL.

## 13. Профиль стартапа и бизнес-модель

Система определяет одну или несколько гипотез модели:

- SaaS;
- marketplace;
- e-commerce;
- fintech;
- consumer application;
- B2B service;
- hardware;
- AI tool или platform;
- hybrid model.

Результат содержит confidence и основания. При неоднозначности система показывает несколько гипотез, но не блокирует первичный анализ: сначала применяются универсальные метрики и общие проверки. Подтверждение модели предлагается как один из приоритетных вопросов глубинного анализа. Исправление пользователя не стирает историю исходного inference.

## 14. Evidence Ledger и claim–evidence matrix

Evidence Ledger является центральным слоем истины. Он отделяет исходный факт, детерминированный расчёт, аналитический вывод и отсутствие данных.

Правила:

1. У каждого факта есть provenance и locator.
2. Критическая цифра без периода и единицы считается неполной.
3. Конфликтующие значения существуют одновременно до разрешения.
4. LLM не создаёт verified evidence без доступного источника.
5. Любое изменение источника инвалидирует зависимые calculations и findings.
6. В пользовательском интерфейсе и отчёте используются понятные метки SOURCE, CALCULATION, INFERENCE и MISSING.
7. High-severity unsupported recommendation не может быть представлена как установленный факт.

Приоритет источников по умолчанию:

1. Подписанный или официальный документ и system export.
2. Аудированная или однозначно воспроизводимая таблица.
3. Management-provided narrative.
4. Rights-cleared market/news data.
5. Вторичный агрегатор.
6. Model inference.

## 15. Metric Pack Engine

Metric pack состоит из четырёх слоёв:

1. Универсальные метрики состояния и качества данных.
2. Метрики бизнес-модели.
3. Метрики стадии развития.
4. Вертикальные risk и compliance signals.

| Модель | Базовые метрики и сигналы |
|---|---|
| Любой стартап | revenue, gross margin, cash, net burn, runway, growth, evidence coverage |
| SaaS | MRR, ARR, churn, NRR, CAC, LTV, LTV/CAC, CAC payback, cohort retention |
| Marketplace | GMV, take rate, liquidity, repeat rate, supply/demand balance, concentration |
| E-commerce | AOV, contribution margin, repeat purchase, return rate, CAC, inventory pressure |
| FinTech | transaction volume, take rate, loss/fraud signals, unit margin, regulatory dependencies |
| Consumer | activation, retention cohorts, engagement, paid conversion, referral |
| B2B service | ACV, pipeline conversion, sales cycle, utilization, delivery margin |
| Hardware | BOM margin, inventory turns, cash conversion, warranty and working-capital risk |
| AI product | inference cost, gross margin, usage depth, retention, data dependency and moat signals |

Каждая карточка метрики содержит:

- название простым языком;
- почему метрика важна;
- формулу и версию;
- необходимые входные данные;
- найденное значение и период;
- confidence и warnings;
- benchmark только при наличии сопоставимого датированного источника;
- отсутствующие данные;
- рекомендуемый способ начать измерение.

Канонические значения рассчитываются локальным Metric Engine с фиксированной precision. OpenAI Code Interpreter разрешён для exploratory анализа публичных или явно одобренных очищенных данных. Любое число из Code Interpreter, которое попадает в отчёт, повторно рассчитывается или валидируется локально.

## 16. Adaptive Question Engine

Система ранжирует вопросы по влиянию:

1. Критические риски и противоречия.
2. Входы для обязательных метрик.
3. Product/market validation.
4. GTM и positioning.
5. Улучшение полноты отчёта.

Допустимые ответы:

- точное значение;
- диапазон или оценка с маркировкой assumption;
- выбор варианта;
- свободный текст;
- подтверждение или исправление извлечённого значения;
- загрузка supporting document;
- unknown или skip.

Если пользователь не знает ответ, система продолжает работу, снижает confidence, показывает влияние пропуска и создаёт действие по сбору данных.

## 17. Launch Readiness и рекомендации

Launch Readiness не должен быть магическим единым числом. Результат состоит из:

- score по отдельным измерениям;
- confidence;
- evidence coverage;
- critical blockers;
- unresolved contradictions;
- версии методологии.

Измерения первой версии:

- Problem Validation;
- Customer and ICP Clarity;
- Market Attractiveness;
- Competitive Position;
- Business Model Clarity;
- Unit Economics;
- GTM Readiness;
- Execution and Regulatory Risk;
- Evidence Quality.

Точные веса версионируются и калибруются на frozen datasets. Отсутствие данных не должно автоматически трактоваться как плохой бизнес: оно снижает evidence confidence и создаёт gap. Любая рекомендация содержит причину, evidence, затрагиваемый риск, предлагаемый эксперимент и ожидаемый результат.

## 18. Market, Competitor, News и Sentiment Analysis

Система формирует research-backed signals, а не заявляет абсолютную полноту рынка.

Обязательная классификация конкурентного пространства:

- direct competitors;
- indirect competitors;
- substitutes;
- do-nothing alternative;
- potential entrants;
- public comparable companies.

Каждый внешний вывод содержит URL или locator, publisher, published/retrieved date, as-of, source class и confidence. TAM, SAM и SOM показываются только вместе с методом расчёта, assumptions и источниками.

Sentiment является вторичным сигналом. Для продаваемого демо обязательна polarity по доступным news/public sources. Полноценная social-media аналитика разрешается только после подключения легального и устойчивого API; отсутствие такого API должно быть видно как coverage limitation.

SEC является первичным источником для SEC-reporting comparables. Yahoo Finance или yfinance остаётся research/demo convenience и не может быть единственным источником критической цифры.

## 19. Plan-and-Execute и специализированные роли

LangGraph управляет типизированным планом, зависимостями, budgets, retries, checkpoints, HITL и stop conditions.

Специализированные роли первой версии:

- Document Intelligence — inventory, parsing и извлечение;
- Startup Profile — модель бизнеса, стадия, ICP и assumptions;
- Product Validation — проблема, ценность и validation evidence;
- Market & Competitor — рынок, конкуренты, substitutes и comparables;
- Financial — метрики и unit economics;
- GTM — каналы, эксперименты и launch plan;
- Risk — market, customer, product, financial, regulatory и execution risks;
- Critic — counter-evidence и contradiction search;
- Arbiter — финальный синтез и приоритеты.

Эти роли реализуются как bounded graph nodes с общим состоянием и Evidence Ledger. Они не являются постоянно работающими отдельными процессами. Оркестратор запускает только те роли, которые нужны кейсу, и может параллелить независимые исследования в пределах бюджета.

## 20. Reflexion и Human-in-the-loop

Reflexion выполняет draft review, counter-evidence retrieval и evidence verification. Ограничения:

- максимум две итерации;
- каждая итерация должна добавить evidence или изменить status;
- critic не изменяет исходные facts и calculations;
- отсутствие прогресса завершает цикл;
- unresolved critical conflict передаётся человеку.

Runtime gates:

- Gate 1 — подтверждение scope, режима, периода и документов;
- Gate 2 — подтверждение разрешённого redacted disclosure scope;
- Gate 3 — решение по критическим противоречиям;
- Gate 4 — заморозка Report Snapshot перед final PDF.

Отказ Gate 2 не блокирует безопасную локальную детерминированную обработку. Отказ Gate 4 запрещает final PDF, но позволяет сохранить явно маркированный draft.

## 21. Отчёт и визуализации

Канонический результат — неизменяемый versioned Report JSON. HTML и PDF являются представлениями одного snapshot.

Обязательные разделы Startup Report:

1. Метаданные, as-of, версия и trace ID.
2. Executive Summary.
3. Startup Profile.
4. Launch thesis и counter-thesis.
5. Launch Readiness и evidence confidence.
6. Сильные стороны.
7. Слабые стороны и blockers.
8. Product Validation.
9. Market, competition и sentiment.
10. Business Model и Metric Pack.
11. Unit Economics и financial outlook.
12. GTM strategy и validation experiments.
13. Risk matrix.
14. Claim–evidence matrix.
15. Contradictions и missing data.
16. Adaptive questions.
17. План 7/30/60/90.
18. Source и calculation appendix.
19. Methodology, assumptions и limitations.
20. Disclaimer и decision-owner statement.

Визуализации:

- readiness dimensions;
- evidence coverage;
- risk heatmap;
- revenue, burn и runway при наличии данных;
- unit economics;
- cohort retention при наличии cohort data;
- competitor positioning;
- action priority по impact и effort.

## 22. Архитектура верхнего уровня

Поток системы:

Founder Workspace → Application Services → Startup или Public Workflow → Evidence Ledger → Metric Engine и Research Adapters → Risk/Reflexion → Report Snapshot → JSON/HTML/PDF.

Параллельный технический контур:

Admin Console → Audit, LangSmith, OpenTelemetry, Evaluation, Privacy, Budgets, Sources и Report Integrity.

Выбранный архитектурный стиль — modular monolith с ports and adapters. Domain не зависит от Streamlit, OpenAI, SEC, конкретной базы данных или report renderer. Startup и Public workflows разделены, но используют общий evidence, metrics, privacy, tracing, approvals и reporting core.

## 23. Технологический стек

### 23.1 Утверждённые архитектурные ограничения и базовые технологии

| Область | Технология | Назначение |
|---|---|---|
| Язык и окружение | Python 3.12/3.13, uv, lockfile | Воспроизводимый backend и dependency profiles |
| Контракты | Pydantic | Строгие входы, результаты узлов и structured outputs |
| Workflow | LangGraph | Plan-and-Execute, checkpoints, branching, HITL и bounded loops |
| AI API | OpenAI Python SDK и Responses API | Structured extraction, analysis и controlled tools |
| Аналитика | Python Metric Engine, Pandas, DuckDB | Канонические метрики и табличный анализ |
| Exploratory code | OpenAI Code Interpreter adapter | Только разрешённые данные и локальная перепроверка чисел |
| Локальное хранение | SQLite и filesystem | Metadata, approvals, checkpoints и artifacts |
| Retrieval | sentence-transformers и FAISS | Локальный multilingual evidence retrieval |
| Public data | SEC EDGAR/XBRL, optional yfinance adapter | Filings и public comparables |
| News research | RSS, GDELT и сменные web adapters | Датированные market/news signals |
| Документы | PyMuPDF, pdfplumber, python-docx, openpyxl, Pillow | Parsing PDF, DOCX, XLSX, CSV и изображений |
| OCR | Tesseract adapter, optional Docling | Локальная обработка сканов и сложных документов |
| Privacy | Rules, optional Presidio, Data Egress Policy | Classification, redaction и external-call control |
| Графики | Plotly и Matplotlib | Interactive и deterministic static charts |
| Отчёты | Jinja2, WeasyPrint, ReportLab fallback | HTML/PDF из канонического snapshot |
| AI tracing | LangSmith adapter | Sanitized AI runs, models, cost и eval linkage |
| App tracing | OpenTelemetry | Application, parser, source и renderer spans |
| Надёжный audit | Durable sanitized local JSONL | Каноническая локальная история даже без exporters |
| Evaluation | pytest, frozen fixtures, Ragas и custom evaluators | Regression, evidence, privacy и numerical quality |

Точные версии библиотек фиксируются lockfile. Model IDs и поставщики являются конфигурацией routing policy, а не неизменяемым продуктовым требованием.

### 23.2 Delivery profiles и решение владельца

| Profile | Возможная поставка | Статус |
|---|---|---|
| A — Capstone Demo Fast | Premium Streamlit для Founder Workspace и Admin Console | Не выбран |
| B — Sales-Ready Hybrid | Product-grade Founder frontend поверх Python application/API; Admin Console временно может остаться на Streamlit | Выбран владельцем 2026-08-11 |
| C — Full Platform First | Next.js/FastAPI self-hosted stack | Не выбран; возможен после Sellable Demo |

Выбор profile B не требует переписывать готовый Python core. Конкретный frontend framework, границы API и способ временного размещения Admin Console фиксируются в отдельном implementation plan после закрытия остальных параметров Decision Gate 0. Независимо от framework обязательны браузерный доступ, разделение Founder/Admin, стабильные application-service boundaries, воспроизводимость и выполнение UX acceptance criteria.

## 24. AI boundary и model routing

Ни один workflow node не вызывает внешний LLM напрямую. Единый gateway выполняет policy check, sensitivity classification, context minimization, redaction, allow/deny, budget check, model routing, structured output validation и безопасную trace metadata запись.

Правила AI:

- неизвестное значение возвращается как отсутствующее с причиной;
- confidence не заменяет evidence;
- каждый существенный claim содержит evidence references;
- schema repair допускается не более одного раза;
- fallback повторно проходит privacy и budget policies;
- restricted content никогда не отправляется внешнему провайдеру;
- model names могут обновляться без изменения domain contracts.

## 25. Privacy и безопасность

Классы данных:

- PUBLIC — публичные filings, страницы и новости;
- INTERNAL — непубличные материалы без прямых identifiers;
- CONFIDENTIAL — финансовые модели, customer data, договоры и cap table;
- RESTRICTED — PII, банковские реквизиты, credentials и особо чувствительные данные.

RESTRICTED остаётся локальным. CONFIDENTIAL может использовать внешний AI только после redaction, minimization и Gate 2. Raw startup artifacts не попадают в LangSmith, OpenTelemetry, tool logs или report telemetry.

Обязательные controls:

- content-addressed storage;
- MIME sniffing и quarantine;
- safe archive handling;
- secrets только через environment или secret store;
- append-only audit;
- server-owned sanitized report templates;
- per-case retention policy;
- zero raw sensitive content в traces;
- default-deny для нового внешнего канала передачи.

## 26. Ошибки и degraded behavior

Пользовательский интерфейс различает:

- отсутствующие данные;
- неподдерживаемый формат;
- quarantined file;
- низкую уверенность OCR или parser;
- недоступный внешний источник;
- реальное противоречие;
- неподтверждённый inference;
- заблокированный privacy call;
- draft report без final approval.

Некритичный source или artifact failure переводит соответствующую часть в partial, но не уничтожает весь кейс. Невозможность сохранить durable audit блокирует новые external AI calls и final report freeze. PDF render failure сохраняет канонический JSON и HTML для повторного rendering.

## 27. Нефункциональные требования

### 27.1 Воспроизводимость

Каждый final report связан с source hashes, data revision, graph, prompt, model, parser, formula, dependency lock, build и trace IDs.

### 27.2 Производительность демо

На внутреннем frozen наборе документов на reference machine:

- UI подтверждает действие не позднее двух секунд;
- inventory preview появляется не позднее десяти секунд после безопасного локального ingest;
- первый actionable Startup Scan результат появляется не позднее 90 секунд;
- полный cached/offline demo report формируется не позднее пяти минут без учёта HITL ожидания;
- общий Startup workflow на произвольном поддерживаемом кейсе имеет blocking offline threshold до 30 минут без учёта HITL.

### 27.3 Надёжность

- checkpoints позволяют продолжить анализ после process restart;
- retries имеют конечный лимит;
- budget policy запрещает новый AI call, превышающий лимит;
- exporter outage не ломает анализ при исправном local audit.

### 27.4 Доступность и responsive behavior

- desktop-first investor demo на ширине 1440;
- WCAG AA contrast;
- risk передаётся не только цветом;
- keyboard-accessible upload и navigation;
- видимые focus states;
- читаемые таблицы и expandable evidence;
- на мобильном доступен упрощённый review, сложные matrices ориентированы на desktop.

## 28. Evaluation и тестовая стратегия

Обязательные наборы:

- public_us_frozen_v1;
- startup_synthetic_saas_v1;
- дополнительные frozen cases для marketplace, e-commerce и fintech metric packs;
- document_parsing_v1;
- privacy_v1;
- report structural snapshots;
- demo journey UI fixture.

Frozen cases разных бизнес-моделей нужны только для внутренней проверки автоматической классификации и metric packs. Они не превращаются в пользовательский выбор проекта или отрасли.

Blocking evaluation acceptance:

Этот раздел задаёт измеримые автоматизированные пороги качества. Он не дублирует продуктовую приёмку демо: единственным источником продуктовых критериев является раздел 34.

| Область | Критерий |
|---|---|
| Critical evidence coverage | 100 процентов critical findings имеют evidence, calculation или insufficient data |
| Unsupported critical claims | 0 процентов неподтверждённых claims представлены как факты |
| Numerical accuracy | 100 процентов golden calculations проходят |
| Contradictions | 100 процентов planted critical conflicts обнаружены |
| Reflexion | Не более двух итераций во всех fixtures |
| Privacy | 0 raw PII, secrets или document-content leaks |
| Trace completeness | 100 процентов завершённых graph nodes имеют local audit event |
| Report completeness | 100 процентов обязательных разделов и disclaimers присутствуют |
| Metric pack coverage | Для каждого frozen business-model case выбраны все обязательные core metrics |
| Missing-data honesty | 0 invented values при отсутствующих обязательных входах |
| Adaptive questions | Каждый critical missing input имеет вопрос или действие по сбору доказательства |
| Market provenance | Каждый competitor, market и sentiment claim имеет источник и as-of либо маркировку local-only inference |
| Readiness determinism | Одинаковый snapshot и версия методологии дают одинаковый score |
| No-prompt journey | Frozen startup case запускается и завершается без пользовательского промпта |
| Checkpoint recovery | Public и Startup workflow продолжаются после имитированного restart |

## 29. Визуальное направление

Founder Workspace использует профессиональную тёмную аналитику: deep navy или near-black фон, cyan/teal для системных сигналов, amber и red только для предупреждений и риска. Человеческий текст остаётся крупным и читаемым; monospace применяется для IDs, hashes, traces и formulas.

Интерфейс должен выглядеть как аналитический продукт, а не как стандартная Streamlit-форма, developer console или Bloomberg-клон. Не допускаются generic purple AI gradients, чрезмерный terminal noise, мелкие low-contrast таблицы и финансовый жаргон без объяснения.

Founder Workspace показывает вывод и путь к действию. Admin Console показывает техническую глубину.

## 30. Сценарий продаваемого демо

Для воспроизводимой проверки команда поддерживает внутренний набор документов, который загружается через тот же интерфейс, что и документы реального пользователя. Этот набор не показывается пользователю как каталог проектов или выбор отрасли. Он должен содержать:

- pitch deck;
- финансовую таблицу;
- customer или cohort CSV;
- один скан с low-confidence OCR;
- один повреждённый или unsupported файл;
- противоречия по ARR, margin, runway и customer count;
- достаточно корректных данных для полезного результата.

Демонстрация должна последовательно показать:

1. Загрузку документа или набора документов через универсальный Data Room.
2. Safety inventory и понятный Data Room coverage.
3. Автоматический первичный анализ без промпта и выбора отрасли.
4. Startup Profile, распознанную бизнес-модель, strengths, weaknesses и gaps.
5. Переход к глубинному анализу того же кейса.
6. Launch Readiness и Metric Pack с объяснением незнакомой метрики.
7. Market & Competitors с public comparable.
8. Найденное критическое противоречие.
9. Три адаптивных вопроса.
10. План 7/30/60/90.
11. PDF preview и download.
12. Admin Agent Graph, privacy и evaluation proof.

Демо должно быть воспроизводимым без оплаченного внешнего API благодаря frozen/cached режиму. Live research является отдельным улучшением и всегда помечается как live.

## 31. Что не входит в продаваемое демо

- автоматическое принятие инвестиционного решения;
- юридическое, налоговое или бухгалтерское заключение;
- автоматическое совершение сделки;
- полноценная Virtual Data Room с sharing, e-signature и granular permissions;
- массовый social scraping без официального API;
- гарантия полноты рынка и списка конкурентов;
- production market-data licensing;
- multi-tenant SaaS, billing и enterprise RBAC;
- обучение собственной foundation model;
- микросервисы ради демонстрации;
- скрытая передача raw startup data внешнему AI.

## 32. Основные риски и меры контроля

| Риск | Мера контроля |
|---|---|
| Продукт превращается в generic AI chat | No-prompt acceptance, workflow-first UI, metric packs и evidence ledger |
| Красивый, но выдуманный вывод | Source/calculation labels, insufficient data и bounded Reflexion |
| Ошибка в арифметике | Только versioned deterministic Metric Engine |
| Readiness воспринимается как абсолютная истина | Отдельные score, confidence, coverage и methodology version |
| Неверные или устаревшие конкуренты | Sources, as-of, confidence и partial coverage |
| Social sentiment переоценён | Только secondary signal и явный coverage disclaimer |
| Утечка data room | Local parsing, Gate 2, redaction, default-deny и privacy tests |
| Слишком широкий MVP | Sellable demo scope и отдельные post-demo stages |
| Слишком много агентов | Специализированные conditional nodes, а не постоянно работающий agent zoo |
| Зависимость от внешней сети | Frozen fixtures, cache и partial behavior |
| Premium UI ломает готовый backend | Стабильные application services и presentation-only integration |
| Невоспроизводимый PDF | Канонический immutable Report JSON и manifest |

## 33. Решения владельца и оставшиеся параметры

Подтверждённое решение:

- 2026-08-11 выбран вариант B — Sales-Ready Hybrid. Founder Workspace получает отдельный product-grade frontend поверх Python application/API backend; Admin Console на первой стадии может переиспользовать Streamlit.
- Пользователь не выбирает demo vertical, тип стартапа или подготовленный проект. Система определяет бизнес-модель из загруженных документов и последовательно формирует первичный и глубинный анализ одного кейса.
- Market research работает по combined policy: использует guarded live sources, когда это разрешено и доступно, а при отсутствии сети или оплаченного API применяет датированный cached/frozen fallback. Пользователь не выбирает технический research mode; интерфейс показывает источник, as-of и ограничения покрытия.

Остаётся выбрать:

1. Финальное публичное название продукта и язык первого рынка.
2. Глубину OCR/redaction adapters в первой поставке.
3. Формат пилота после демо: local desktop, hosted single-tenant или self-hosted.
4. Pricing и коммерческую упаковку после подтверждения полезности демо.

Эти открытые решения не отменяют выбранный profile B, но блокируют соответствующие ветки implementation plan.

## 34. Итоговые критерии приёмки продаваемого демо

Демо считается готовым к показу только когда одновременно выполняются условия:

- основной стартовый сценарий — Startup Launch Analyzer;
- пользователь загружает материалы без выбора отрасли и получает первичный анализ без промпта;
- в том же кейсе доступен глубинный анализ без повторной загрузки документов;
- система показывает профиль, сильные стороны, блокеры, конкурентов и metric pack;
- missing data превращается в адаптивные вопросы и действия;
- присутствует как минимум одно найденное доказуемое противоречие;
- рекомендации связаны с evidence и не маскируют assumptions;
- Public Company используется как вторичный comparable module;
- Founder Workspace и Admin Console визуально и функционально разделены;
- Admin Console показывает tracing, privacy, eval и cost/latency без raw sensitive data;
- JSON, HTML и PDF построены из одного approved snapshot;
- Gate C, D и E проходят на frozen fixtures;
- все обязательные capstone-технологии представлены либо работающим пользовательским сценарием, либо честно маркированным secondary signal;
- интерфейс прошёл отдельный screenshot review на desktop 1440 и не выглядит как стандартный инженерный Streamlit-прототип.

## 35. Связанные документы

- [Предыдущая umbrella-спецификация](2026-08-09-investment-due-diligence-agent-design.md).
- [Текущий подробный Public Company plan](../plans/2026-08-09-public-company-local-mvp.md).
- [Базовый Startup implementation plan](../plans/2026-08-09-startup-data-room-local-mvp.md).
- [Обновлённый управляющий roadmap](../plans/2026-08-11-founder-launch-intelligence-delivery-roadmap.md).

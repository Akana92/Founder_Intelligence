import type {
  FounderReportSectionStatus,
  StartupGtmResponse,
  StartupProfileResponse,
  StartupReportSnapshotResponse,
} from "@/lib/contracts";
import { buildFounderReadinessPresentation } from "@/lib/readiness-presentation";

function reportStatusLabel(status: FounderReportSectionStatus): string {
  if (status === "confirmed") return "Подтверждено";
  if (status === "partial") return "Частично";
  if (status === "contradiction") return "Противоречие";
  return "Нужно доказательство";
}

const deepSectionLabels = {
  market_size: "Рынок",
  competitors: "Конкуренты",
  risks: "Риски",
  action_plan: "Следующие действия",
} as const;

function founderStageStatus(status: string): string {
  if (status === "available") return "available";
  if (status === "lineage_mismatch") return "needs-sync";
  return "pending";
}

function founderStageStatusLabel(status: string): string {
  if (status === "available") return "Данные согласованы";
  if (status === "lineage_mismatch") return "Версии не совпадают";
  return "Готовность ещё не рассчитана";
}

export function FounderReadinessPanel({
  profile,
  gtm,
  reportCaseId,
  reportSnapshot,
}: Readonly<{
  profile: StartupProfileResponse | null;
  gtm: StartupGtmResponse | null;
  reportCaseId?: string | null;
  reportSnapshot: StartupReportSnapshotResponse | null;
}>) {
  if (!profile || !gtm || !reportSnapshot) return null;
  const presentation = buildFounderReadinessPresentation({
    profile,
    gtm,
    reportCaseId: reportCaseId ?? null,
    reportSnapshot,
  });
  const lineageMismatch = presentation.stages.some(
    (stage) => stage.status === "lineage_mismatch",
  );

  return (
    <section
      aria-labelledby="founder-readiness-title"
      className="founder-readiness"
      data-readiness-panel
    >
      <header className="founder-readiness__header">
        <div>
          <span className="section-kicker">Готовность и глубинная проверка</span>
          <h2 id="founder-readiness-title">
            Что подтверждено, что блокирует решение и что спросить дальше
          </h2>
          <p>
            Панель читает только подтверждённый отчёт. Она не пересчитывает
            метрики и не превращает пробелы в оценки.
          </p>
        </div>
      </header>

      <div className="founder-readiness__stages" aria-label="Состояния анализа">
        {presentation.stages.map((stage) => (
          <article
            data-analysis-stage={stage.key}
            data-analysis-status={founderStageStatus(stage.status)}
            key={stage.key}
          >
            <span>{stage.key === "primary" ? "Уровень 1" : "Уровень 2"}</span>
            <h3>{stage.key === "primary" ? "Первичный контур" : "Глубинный контур"}</h3>
            <strong>{founderStageStatusLabel(stage.status)}</strong>
          </article>
        ))}
      </div>

      {lineageMismatch ? (
        <div className="founder-readiness__warning" role="alert">
          Данные профиля, GTM и отчёта относятся к разным версиям. Глубинные
          выводы скрыты до синхронизации кейса.
        </div>
      ) : (
        <>
          <section className="founder-readiness__dimensions" aria-label="Готовность метрик">
            <div className="founder-readiness__section-head">
              <div>
                <span className="section-kicker">Проверки решения</span>
                <h3>Проверки готовности</h3>
              </div>
              <span>
                {presentation.readiness.status === "available"
                  ? `${presentation.readiness.dimensionCards.length} проверок`
                  : "Проверки пока недоступны"}
              </span>
            </div>
            {presentation.readiness.dimensionCards.length > 0 ? (
              <div className="readiness-dimension-grid">
                {presentation.readiness.dimensionCards.map((card, index) => (
                  <article
                    data-readiness-dimension={card.key}
                    key={`${index}-${card.key}`}
                  >
                    <div>
                      <h4>{card.labelRu}</h4>
                      <span>{card.statusLabelRu}</span>
                    </div>
                    <p>{card.explanationRu}</p>
                  </article>
                ))}
              </div>
            ) : (
              <p className="founder-readiness__empty">
                Детализация готовности отсутствует в подтверждённом отчёте.
              </p>
            )}
          </section>

          <div className="founder-readiness__deep-grid">
            {presentation.deepSections.map((section) => (
              <article
                className={`deep-summary deep-summary--${section.status.toLowerCase()}`}
                data-deep-section={section.key}
                data-deep-status={section.status}
                key={section.key}
              >
                <div className="deep-summary__head">
                  <h3>{deepSectionLabels[section.key]}</h3>
                  <span>{reportStatusLabel(section.status)}</span>
                </div>
                <p>{section.summary}</p>
                <dl>
                  <div>
                    <dt>Строки доказательств</dt>
                    <dd>{section.rows.length}</dd>
                  </div>
                  <div>
                    <dt>Открытые пункты</dt>
                    <dd>{section.items.length}</dd>
                  </div>
                </dl>
              </article>
            ))}
          </div>

          <div className="founder-readiness__followups">
            <section aria-labelledby="founder-readiness-gaps-title">
              <h3 id="founder-readiness-gaps-title">Что сделать дальше</h3>
              {presentation.gaps.length > 0 ? (
                <ul>
                  {presentation.gaps.map((gap, index) => (
                    <li key={`${index}-${gap}`}>{gap}</li>
                  ))}
                </ul>
              ) : (
                <p>В каноническом снимке нет открытых пробелов.</p>
              )}
            </section>
            <section aria-labelledby="founder-readiness-questions-title">
              <h3 id="founder-readiness-questions-title">Приоритетные вопросы</h3>
              {presentation.questions.length > 0 ? (
                <ol>
                  {presentation.questions.map((question, index) => (
                    <li key={`${index}-${question}`}>{question}</li>
                  ))}
                </ol>
              ) : (
                <p>Дополнительные вопросы для этого снимка не сформированы.</p>
              )}
            </section>
          </div>
        </>
      )}
    </section>
  );
}

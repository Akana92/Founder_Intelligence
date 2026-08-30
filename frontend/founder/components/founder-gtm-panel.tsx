import type { StartupGtmResponse } from "@/lib/contracts";
import { buildStartupGtmPresentation } from "@/lib/gtm-presentation";

function dimensionAction(status: string): string {
  if (status === "supported") return "Можно использовать в запуске.";
  if (status === "partial") return "Уточните недостающие доказательства перед масштабированием.";
  if (status === "contradicted") return "Сначала разберите противоречие с командой.";
  return "Нужно добавить проверяемое доказательство.";
}

export function StartupGtmPanel({
  gtm,
}: Readonly<{ gtm: StartupGtmResponse | null }>) {
  if (!gtm) return null;
  const presentation = buildStartupGtmPresentation(gtm);

  return (
    <section aria-labelledby="startup-gtm-title" className="startup-gtm">
      <header className="startup-gtm__header">
        <div>
          <span className="section-kicker">Замороженный GTM-снимок</span>
          <h2 id="startup-gtm-title">План выхода на рынок</h2>
          <p>
            Только подтверждённые ссылки, явно отмеченные пробелы и эксперименты
            из канонического снимка. Прогнозы результатов не добавляются.
          </p>
        </div>
        <div className="startup-gtm__summary">
          <span className={`gtm-state gtm-state--${presentation.status}`}>
            {presentation.statusLabel}
          </span>
          <span>{presentation.findingCount} вывод(а)</span>
          <a href="/admin">Техническая проверка доступна в кабинете администратора</a>
        </div>
      </header>

      <div className="startup-gtm__dimensions" aria-label="Измерения плана выхода на рынок">
        {presentation.dimensions.map((dimension) => {
          const referenceCount =
            dimension.evidenceFactIds.length +
            dimension.marketSourceIds.length +
            dimension.contradictionIds.length;
          return (
            <article className="gtm-dimension" key={dimension.name}>
              <div className="gtm-dimension__head">
                <h3>{dimension.label}</h3>
                <span className={`gtm-state gtm-state--${dimension.status}`}>
                  {dimension.statusLabel}
                </span>
              </div>
              <dl className="gtm-dimension__counts">
                <div>
                  <dt>Факты</dt>
                  <dd>{dimension.evidenceFactIds.length}</dd>
                </div>
                <div>
                  <dt>Рынок</dt>
                  <dd>{dimension.marketSourceIds.length}</dd>
                </div>
                <div>
                  <dt>Противоречия</dt>
                  <dd>{dimension.contradictionIds.length}</dd>
                </div>
              </dl>
              <div className="gtm-dimension__codes">
                <span>Основание</span>
                <strong>{dimensionAction(dimension.status)}</strong>
              </div>
              {referenceCount > 0 ? (
                <details className="gtm-references">
                  <summary>Доказательства учтены ({referenceCount})</summary>
                  <p>
                    Детальные ссылки и идентификаторы доступны только в
                    администраторской проверке.
                  </p>
                </details>
              ) : null}
            </article>
          );
        })}
      </div>

      <section aria-labelledby="startup-gtm-launch-title" className="startup-gtm__launch">
        <div className="startup-gtm__section-head">
          <span className="section-kicker">План действий</span>
          <h3 id="startup-gtm-launch-title">7 / 30 / 60 / 90 дней</h3>
        </div>
        <div className="gtm-launch-grid">
          {presentation.launchPlan.map((step) => (
            <article key={step.horizon}>
              <span>{step.label}</span>
              <ol>
                {step.experimentLabels.map((label) => (
                  <li key={`${step.horizon}-${label}`}>
                    <strong>{label}</strong>
                  </li>
                ))}
              </ol>
            </article>
          ))}
        </div>
      </section>

      <p className="startup-gtm__lineage">
        Происхождение снимка и технические идентификаторы вынесены в кабинет
        администратора.
      </p>
    </section>
  );
}

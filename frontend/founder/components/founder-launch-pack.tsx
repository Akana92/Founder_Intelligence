"use client";

import { Download, FileText, RefreshCw, ShieldCheck } from "lucide-react";

import type { LaunchPackMetadataResponse } from "../lib/contracts";
import { formatScenario } from "../lib/founder-readable-presentation";

import styles from "./founder-strategy-pages.module.css";

const assetLabels: Readonly<Record<string, string>> = {
  customer_interview_script: "Сценарий интервью с клиентом",
  gtm_launch_pack: "Рабочий пакет выхода на рынок",
  positioning_map: "Карта позиционирования",
  pricing_experiment: "Эксперимент по цене",
  weekly_funnel_template: "Шаблон недельной воронки",
};

const assetDownloadSlugs: Readonly<Record<string, string>> = {
  customer_interview_script: "interview-script",
  gtm_launch_pack: "go-to-market-pack",
  positioning_map: "positioning-map",
  pricing_experiment: "pricing-test",
  weekly_funnel_template: "funnel-template",
};

function assetLabel(assetKey: string): string {
  return assetLabels[assetKey] ?? "Черновик рабочего материала";
}

function assetDownloadSlug(assetKey: string): string {
  return assetDownloadSlugs[assetKey] ?? "work-material";
}

function assetDownloadName(
  launchPack: LaunchPackMetadataResponse,
  extension: "md" | "provenance.md" | "csv",
): string {
  return `${assetDownloadSlug(launchPack.asset_key)}-r${launchPack.asset_revision}.${extension}`;
}

function assetUseGuidance(assetKey: string): string {
  if (assetKey === "customer_interview_script") {
    return "Провести интервью и отдельно занести подтверждённые ответы в данные кейса.";
  }
  if (assetKey === "positioning_map") {
    return "Сверить позиционирование с клиентскими сегментами и конкурентными альтернативами.";
  }
  if (assetKey === "pricing_experiment") {
    return "Запустить проверку цены и отделить ответы основателя от подтверждённых фактов.";
  }
  if (assetKey === "weekly_funnel_template") {
    return "Заполнять недельную воронку и возвращать новые факты через проверяемые источники.";
  }
  return "Использовать как рабочий GTM-черновик для обсуждения, проверки и следующего плана действий.";
}

function launchPackPreviewSections(
  launchPack: LaunchPackMetadataResponse,
): ReadonlyArray<Readonly<{ title: string; body: string }>> {
  const label = assetLabel(launchPack.asset_key);
  return [
    {
      title: "Что это за материал",
      body: `${label}, версия ${launchPack.asset_revision}. Это рабочий черновик по сценарию ${formatScenario(
        launchPack.selected_scenario_key,
      )}, связанный с версией данных ${launchPack.data_revision}.`,
    },
    {
      title: "Как использовать черновик",
      body: `${assetUseGuidance(
        launchPack.asset_key,
      )} Черновик не является доказательством и не записывает новые значения в журнал доказательств.`,
    },
    {
      title: "Что скачать",
      body: launchPack.csv_url
        ? "Полный текст остаётся в скачиваемом Markdown, происхождение данных — в отдельном приложении, а таблица доступна как CSV-экспорт."
        : "Полный текст остаётся в скачиваемом Markdown, а происхождение данных — в отдельном приложении. CSV для этого материала не требуется.",
    },
  ];
}

export function FounderLaunchPack({
  busy = false,
  launchPack,
  onRegenerate,
}: Readonly<{
  busy?: boolean;
  launchPack: LaunchPackMetadataResponse | null | undefined;
  onRegenerate?: () => void;
}>) {
  if (!launchPack) {
    return (
      <section className={styles.panel} data-founder-launch-pack="empty">
        <h2>Рабочий пакет ещё не собран</h2>
        <p>
          Соберите черновик после выбора сценария. Это будет черновик, не являющийся доказательством:
          сценарные метрики сохраняют происхождение данных, формулы, диапазоны и план проверки.
        </p>
        <div className={styles.toolbar}>
          <button
            className={styles.pinkButton}
            disabled={!onRegenerate || busy}
            onClick={onRegenerate}
            type="button"
          >
            Собрать рабочий пакет
            <RefreshCw aria-hidden="true" size={18} />
          </button>
          <span className={styles.researchDisclaimer}>
            <ShieldCheck aria-hidden="true" size={16} />
            Ничего не записывается в журнал доказательств.
          </span>
        </div>
      </section>
    );
  }

  return (
    <section className={styles.panel} data-founder-launch-pack="draft">
      <div className={styles.reportGateHeader}>
        <div>
          <span className={styles.eyebrow}>Черновик рабочего пакета</span>
          <h2>{assetLabel(launchPack.asset_key)} · версия {launchPack.asset_revision}</h2>
          <p>
            Статус: черновик. Версия данных кейса: {launchPack.data_revision}; выбранный
            сценарий: {formatScenario(launchPack.selected_scenario_key)}; набор сценариев связан
            с текущей версией данных.
          </p>
        </div>
        <button
          className={styles.outlineButton}
          disabled={!onRegenerate || busy}
          onClick={onRegenerate}
          type="button"
        >
          Пересобрать
          <RefreshCw aria-hidden="true" size={18} />
        </button>
      </div>

      <div className={styles.formatGrid}>
        <a className={styles.formatCard} download={assetDownloadName(launchPack, "md")} href={launchPack.markdown_url} target="_blank" rel="noreferrer">
          <div className={styles.formatCardHeader}>
            <span className={styles.formatIcon}>
              <FileText aria-hidden="true" size={28} />
            </span>
            <div>
              <strong>Предпросмотр и загрузка Markdown</strong>
              <p className={styles.formatDescription}>
                {launchPack.asset_key === "gtm_launch_pack"
                  ? "Полный черновик с 12 разделами приложения."
                  : "Полный черновик выбранного материала, не являющегося доказательством."}
              </p>
            </div>
          </div>
          <div className={styles.formatStatus} data-ready="true">
            <Download aria-hidden="true" size={18} />
            <span>Открыть Markdown</span>
          </div>
        </a>

        <a className={styles.formatCard} download={assetDownloadName(launchPack, "provenance.md")} href={launchPack.provenance_appendix_url} target="_blank" rel="noreferrer">
          <div className={styles.formatCardHeader}>
            <span className={styles.formatIcon}>
              <ShieldCheck aria-hidden="true" size={28} />
            </span>
            <div>
              <strong>Приложение о происхождении данных</strong>
              <p className={styles.formatDescription}>Диапазоны, формулы, зависимости и план проверки.</p>
            </div>
          </div>
          <div className={styles.formatStatus} data-ready="true">
            <Download aria-hidden="true" size={18} />
            <span>Открыть приложение</span>
          </div>
        </a>

        <article className={styles.formatCard}>
          <div className={styles.formatCardHeader}>
            <span className={styles.formatIcon}>
              <FileText aria-hidden="true" size={28} />
            </span>
            <div>
              <strong>CSV</strong>
              <p className={styles.formatDescription}>
                {launchPack.csv_url
                  ? "CSV доступен для шаблона недельной воронки."
                  : "Для этого материала CSV не поддерживается."}
              </p>
            </div>
          </div>
          {launchPack.csv_url ? (
            <a className={styles.formatStatus} data-ready="true" download={assetDownloadName(launchPack, "csv")} href={launchPack.csv_url} target="_blank" rel="noreferrer">
              <Download aria-hidden="true" size={18} />
              <span>Открыть CSV</span>
            </a>
          ) : (
            <div className={styles.formatStatus} data-ready="false">
              <span>CSV не нужен</span>
            </div>
          )}
        </article>
      </div>

      <div className={styles.markdownPreview}>
        {launchPackPreviewSections(launchPack).map((section) => (
          <section key={section.title}>
            <strong>{section.title}</strong>
            <p>{section.body}</p>
          </section>
        ))}
      </div>
    </section>
  );
}

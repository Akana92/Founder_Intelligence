"use client";

import {
  type ChangeEvent,
  type DragEvent,
  useId,
  useState,
} from "react";
import {
  AlertTriangle,
  Archive,
  CheckCircle2,
  File as FileIcon,
  FileImage,
  FileSpreadsheet,
  FileText,
  MoreHorizontal,
  Trash2,
  UploadCloud,
} from "lucide-react";

import {
  buildLocalInventory,
  formatFileSize,
  type LocalFileInventoryItem,
} from "@/lib/upload";

import styles from "./upload-entry.module.css";

type UploadEntryProps = Readonly<{
  busy?: boolean;
  busyLabel?: string;
  inventory: readonly LocalFileInventoryItem[];
  onFilesSelected?: (files: File[]) => void;
  onInventoryChange: (inventory: LocalFileInventoryItem[]) => void;
  onStartAnalysis?: () => void;
  variant?: "dashboard" | "data-room";
}>;

const emptyMaterialGuides = [
  ["Описание продукта", "Что вы создаёте и для кого", FileText],
  ["Финансовые данные", "Цена, выручка, расходы или план", FileSpreadsheet],
  ["Проверка спроса", "Интервью, пилоты или обратная связь", FileIcon],
  ["Контекст рынка", "Конкуренты, сегмент или заметки", Archive],
] as const;

function cx(...classNames: Array<string | false | null | undefined>): string {
  return classNames.filter(Boolean).join(" ");
}

function fileExtension(name: string): string {
  const extension = name.split(".").at(-1)?.trim().toLocaleUpperCase("ru-RU");
  return extension && extension !== name.toLocaleUpperCase("ru-RU")
    ? extension.slice(0, 4)
    : "FILE";
}

function fileKind(item: LocalFileInventoryItem): string {
  const extension = fileExtension(item.name).toLocaleLowerCase("ru-RU");
  if (extension === "pdf") return "Документ";
  if (extension === "xlsx" || extension === "csv") return "Финансы";
  if (extension === "docx") return "Описание";
  if (["png", "jpg", "jpeg", "webp"].includes(extension)) return "Изображение";
  if (extension === "zip") return "Архив";
  return item.candidateStatus === "candidate" ? "Материал" : "Проверка";
}

function FileKindIcon({ item }: Readonly<{ item: LocalFileInventoryItem }>) {
  const extension = fileExtension(item.name).toLocaleLowerCase("ru-RU");

  if (extension === "pdf" || extension === "docx") {
    return <FileText aria-hidden="true" size={18} strokeWidth={1.9} />;
  }
  if (extension === "xlsx" || extension === "csv") {
    return <FileSpreadsheet aria-hidden="true" size={18} strokeWidth={1.9} />;
  }
  if (["png", "jpg", "jpeg", "webp"].includes(extension)) {
    return <FileImage aria-hidden="true" size={18} strokeWidth={1.9} />;
  }
  if (extension === "zip") {
    return <Archive aria-hidden="true" size={18} strokeWidth={1.9} />;
  }
  return <FileIcon aria-hidden="true" size={18} strokeWidth={1.9} />;
}

export function UploadEntry({
  busy,
  busyLabel,
  inventory,
  onFilesSelected,
  onInventoryChange,
  onStartAnalysis,
  variant = "data-room",
}: UploadEntryProps) {
  const inputId = useId();
  const [dragActive, setDragActive] = useState(false);
  const isBusy = Boolean(busy);
  const busyCopy = busyLabel ?? "Идёт обработка материалов…";
  const selectFilesCopy = isBusy ? busyCopy : "Выбрать файлы";
  const dashboardUploadCopy = isBusy ? busyCopy : "Загрузить проект";
  const startAnalysisCopy = isBusy ? busyCopy : "Запустить анализ выбранных материалов";

  function addFiles(files: FileList | null) {
    if (isBusy) return;
    if (!files) return;
    const selectedFiles = Array.from(files);
    if (selectedFiles.length === 0) return;

    const incoming = buildLocalInventory(selectedFiles);
    const byId = new Map(inventory.map((item) => [item.id, item]));
    incoming.forEach((item) => byId.set(item.id, item));
    onInventoryChange(Array.from(byId.values()));
    onFilesSelected?.(selectedFiles);
  }

  function onChange(event: ChangeEvent<HTMLInputElement>) {
    addFiles(event.target.files);
    event.target.value = "";
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragActive(false);
    if (isBusy) return;
    addFiles(event.dataTransfer.files);
  }

  function removeFile(id: string) {
    if (isBusy) return;
    onInventoryChange(inventory.filter((item) => item.id !== id));
  }

  return (
    <div
      className={cx(
        styles.entry,
        variant === "dashboard" ? styles.dashboardEntry : styles.dataRoomEntry,
      )}
      id="upload"
    >
      <div
        className={cx(styles.dropZone, dragActive && styles.dragging)}
        onDragEnter={(event) => {
          event.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDragOver={(event) => event.preventDefault()}
        onDrop={onDrop}
      >
        <input
          disabled={isBusy}
          id={inputId}
          multiple
          onChange={onChange}
          type="file"
        />
        <div className={styles.uploadIcon} aria-hidden="true">
          <UploadCloud aria-hidden="true" size={48} strokeWidth={1.65} />
        </div>
        <div className={styles.dropCopy}>
          <p className={styles.title}>
            {variant === "dashboard"
              ? "Новый анализ"
              : "Перетащите файлы или выберите на компьютере"}
          </p>
          <p className={styles.copy}>
            {variant === "dashboard"
              ? "Загрузите PDF, DOCX, XLSX, CSV или ZIP"
              : "PDF, DOCX, XLSX, CSV, изображения и безопасный ZIP"}
          </p>
        </div>
        <label
          aria-disabled={isBusy}
          className={styles.primaryButton}
          htmlFor={inputId}
          style={{ pointerEvents: isBusy ? "none" : undefined }}
        >
          {variant === "dashboard" ? dashboardUploadCopy : selectFilesCopy}
        </label>
        {variant === "dashboard" ? (
          <p className={styles.dashboardHint}>Без выбора отрасли и без промпта</p>
        ) : null}
      </div>

      {inventory.length > 0 ? (
        <div className={styles.inventory} aria-live="polite">
          <div className={styles.inventoryHead}>
            <div>
              <span>Неполный набор допустим</span>
              <strong>{inventory.length} файл(а) выбрано</strong>
            </div>
            <button
              className={styles.clearButton}
              disabled={isBusy}
              onClick={() => onInventoryChange([])}
              type="button"
            >
              Очистить
            </button>
          </div>
          <ul className={styles.inventoryList}>
            {inventory.map((file) => (
              <li className={styles.inventoryItem} key={file.id}>
                <span
                  className={cx(
                    styles.fileTypeBadge,
                    file.candidateStatus === "review_required" &&
                      styles.fileTypeBadgeReview,
                  )}
                  aria-hidden="true"
                >
                  <FileKindIcon item={file} />
                  <small>{fileExtension(file.name)}</small>
                </span>
                <span className={styles.fileMain}>
                  <strong>{file.name}</strong>
                  <small>
                    {fileKind(file)} / {formatFileSize(file.size)}
                  </small>
                </span>
                <span
                  className={
                    file.candidateStatus === "candidate"
                      ? styles.readyStatus
                      : styles.reviewStatus
                  }
                >
                  {file.candidateStatus === "candidate" ? (
                    <CheckCircle2 aria-hidden="true" size={18} strokeWidth={1.9} />
                  ) : (
                    <AlertTriangle aria-hidden="true" size={18} strokeWidth={1.9} />
                  )}
                  {file.candidateStatus === "candidate" ? "Готово" : "Нужна проверка"}
                </span>
                <button
                  aria-label={`Убрать ${file.name}`}
                  className={styles.removeButton}
                  disabled={isBusy}
                  onClick={() => removeFile(file.id)}
                  type="button"
                >
                  <Trash2 aria-hidden="true" size={16} strokeWidth={1.9} />
                </button>
                <MoreHorizontal
                  aria-hidden="true"
                  className={styles.moreIcon}
                  size={20}
                  strokeWidth={1.9}
                />
              </li>
            ))}
          </ul>
          {onStartAnalysis ? (
            <button
              className={styles[isBusy ? "disabledButton" : "secondaryButton"]}
              disabled={isBusy}
              onClick={onStartAnalysis}
              type="button"
            >
              {startAnalysisCopy}
            </button>
          ) : null}
        </div>
      ) : variant === "data-room" ? (
        <section className={styles.emptyInventory} aria-label="Что можно добавить">
          <div className={styles.emptyInventoryHead}>
            <strong>Добавленные материалы появятся здесь</strong>
            <span>Можно начать с одного документа</span>
          </div>
          <ul>
            {emptyMaterialGuides.map(([title, detail, Icon]) => (
              <li key={title}>
                <span className={styles.guideIcon} aria-hidden="true">
                  <Icon size={18} strokeWidth={1.75} />
                </span>
                <span>
                  <strong>{title}</strong>
                  <small>{detail}</small>
                </span>
                <em>Можно добавить</em>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

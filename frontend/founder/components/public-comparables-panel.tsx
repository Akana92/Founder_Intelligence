"use client";

import { useEffect, useState } from "react";

import {
  capabilityByKey,
  parseProductCapabilities,
  type LifecycleStatus,
} from "@/lib/contracts";

type ComparablesState =
  | { kind: "loading" }
  | { kind: "ready"; status: LifecycleStatus }
  | { kind: "unavailable" };

const statusCopy: Record<LifecycleStatus, Readonly<{ label: string; detail: string }>> = {
  available: {
    label: "Аналитическое ядро доступно",
    detail:
      "Public-company workflow уже работает как secondary research capability. Отдельный founder-safe запуск кейса будет подключён здесь через Founder API — без перехода в операторскую консоль.",
  },
  planned: {
    label: "Следующая стадия",
    detail:
      "Контракт уже зарезервировал Public Comparables, но запуск пока не открыт. Интерфейс не подменяет отсутствие функции демонстрационными данными.",
  },
  unavailable: {
    label: "Сейчас недоступно",
    detail:
      "Public Comparables отключён в текущем контракте. Основной интерфейс сохраняет этот маршрут отдельно от технического контура.",
  },
};

export function PublicComparablesPanel() {
  const [state, setState] = useState<ComparablesState>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();

    async function load() {
      try {
        const response = await fetch("/api/capabilities", {
          cache: "no-store",
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error("capabilities unavailable");
        }
        const contract = parseProductCapabilities(await response.json());
        setState({
          kind: "ready",
          status: capabilityByKey(contract, "public_comparable_analysis")
            .lifecycle_status,
        });
      } catch {
        if (!controller.signal.aborted) {
          setState({ kind: "unavailable" });
        }
      }
    }

    void load();
    return () => controller.abort();
  }, []);

  if (state.kind === "loading") {
    return (
      <div className="comparables-status" role="status">
        <span className="status-mark" aria-hidden="true" />
        Проверяем capability contract…
      </div>
    );
  }

  if (state.kind === "unavailable") {
    return (
      <div className="comparables-status comparables-status--warning" role="status">
        <span className="warning-icon" aria-hidden="true">
          !
        </span>
        <div>
          <strong>Founder API сейчас недоступен</strong>
          <p>
            Статус Public Comparables нельзя подтвердить. Мы не открываем Admin Console
            и не показываем вымышленные результаты.
          </p>
        </div>
      </div>
    );
  }

  const copy = statusCopy[state.status];
  return (
    <div className={`comparables-status comparables-status--${state.status}`} role="status">
      <span className="status-mark" aria-hidden="true" />
      <div>
        <span className="comparables-status__eyebrow">{state.status}</span>
        <strong>{copy.label}</strong>
        <p>{copy.detail}</p>
      </div>
    </div>
  );
}

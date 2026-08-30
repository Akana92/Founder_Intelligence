"use client";

import { useEffect, useState } from "react";

import {
  parseProductCapabilities,
} from "@/lib/contracts";
import {
  presentCapabilityBoundary,
  type CapabilityBoundaryLoadState,
} from "@/lib/capability-presentation";

export function CapabilityStatus() {
  const [state, setState] = useState<CapabilityBoundaryLoadState>({
    kind: "loading",
  });

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
        setState({ kind: "ready", contract });
      } catch {
        if (!controller.signal.aborted) {
          setState({ kind: "unavailable" });
        }
      }
    }

    void load();
    return () => controller.abort();
  }, []);

  const presentation = presentCapabilityBoundary(state);

  if (presentation.kind === "loading") {
    return (
      <div className="capability-state capability-state--loading" role="status">
        <span className="status-mark" aria-hidden="true" />
        {presentation.title}
      </div>
    );
  }

  if (presentation.kind === "unavailable") {
    return (
      <div className="capability-state capability-state--warning" role="status">
        <span className="warning-icon" aria-hidden="true">
          !
        </span>
        <div>
          <strong>{presentation.title}</strong>
          <p>{presentation.detail}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="capability-contract">
      <div className="capability-state capability-state--ready" role="status">
        <span className="status-mark" aria-hidden="true" />
        <div>
          <strong>{presentation.title}</strong>
          <p>{presentation.detail}</p>
        </div>
      </div>
      <ul aria-label="Статус возможностей продукта">
        {presentation.capabilities.map((capability) => (
          <li key={capability.key}>
            <span>{capability.label}</span>
            <span className={`lifecycle lifecycle--${capability.lifecycle}`}>
              {capability.lifecycleLabel}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

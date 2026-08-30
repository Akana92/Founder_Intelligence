from __future__ import annotations

import importlib
import os
from collections.abc import Callable, Mapping
from math import isfinite

from pydantic import BaseModel, ConfigDict

from due_diligence_agent.adapters.observability.privacy import StrictTraceSanitizer


class LangSmithTraceConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = False


class LangSmithCallbacks(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    client: object | None
    metadata: Mapping[str, str | int | float | bool | None]

    def hide_inputs(self, inputs: Mapping[str, object]) -> dict[str, object]:
        return _sanitize_io(inputs)

    def hide_outputs(self, outputs: Mapping[str, object]) -> dict[str, object]:
        return _sanitize_io(outputs)


class LangSmithTraceAdapter:
    def __init__(
        self,
        config: LangSmithTraceConfig,
        *,
        client_factory: Callable[..., object] | None = None,
        sanitizer: StrictTraceSanitizer | None = None,
    ) -> None:
        self._config = config
        self._client_factory = client_factory
        self._sanitizer = sanitizer or StrictTraceSanitizer()
        self._client: object | None = None

    @property
    def client(self) -> object | None:
        if not self._config.enabled:
            return None
        return self._load_client()

    def callbacks(self, *, metadata: Mapping[str, object | None]) -> LangSmithCallbacks:
        if not self._config.enabled:
            return LangSmithCallbacks(client=None, metadata={})
        safe_metadata = self._sanitizer.sanitize_attributes(metadata, drop_disallowed=True)
        client = self._load_client()
        return LangSmithCallbacks(client=client, metadata=safe_metadata)

    def _load_client(self) -> object:
        if self._client is None:
            os.environ["LANGSMITH_HIDE_INPUTS"] = "true"
            os.environ["LANGSMITH_HIDE_OUTPUTS"] = "true"
            kwargs = {
                "hide_inputs": _hide_inputs,
                "hide_outputs": _hide_outputs,
                "hide_metadata": self._hide_metadata,
                "omit_traced_runtime_info": True,
            }
            if self._client_factory is not None:
                self._client = self._client_factory(**kwargs)
            else:
                module = importlib.import_module("langsmith")
                api_key = os.environ.get("LANGSMITH_API_KEY") or os.environ.get(
                    "LANGCHAIN_API_KEY"
                )
                if api_key:
                    kwargs["api_key"] = api_key
                self._client = module.Client(**kwargs)
        return self._client

    def _hide_metadata(
        self,
        metadata: Mapping[str, object | None],
    ) -> dict[str, object]:
        flat_metadata = {
            key: value for key, value in metadata.items() if key != "usage_metadata"
        }
        safe: dict[str, object] = dict(
            self._sanitizer.sanitize_attributes(flat_metadata, drop_disallowed=True)
        )
        usage_metadata = _sanitize_usage_metadata(metadata.get("usage_metadata"))
        if usage_metadata:
            safe["usage_metadata"] = usage_metadata
        return safe


def _hide_inputs(inputs: Mapping[str, object]) -> dict[str, object]:
    return _sanitize_io(inputs)


def _hide_outputs(outputs: Mapping[str, object]) -> dict[str, object]:
    return _sanitize_io(outputs)


def _sanitize_io(payload: Mapping[str, object]) -> dict[str, object]:
    sanitizer = StrictTraceSanitizer()
    safe: dict[str, object] = {}
    for key, value in payload.items():
        try:
            sanitized = sanitizer.sanitize_attributes({key: value})
        except ValueError:
            continue
        if sanitized.get(key) is not None:
            safe[key] = sanitized[key]
    return safe


def _sanitize_usage_metadata(value: object | None) -> dict[str, int | float]:
    if not isinstance(value, Mapping):
        return {}
    safe: dict[str, int | float] = {}
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        candidate = value.get(key)
        if isinstance(candidate, bool) or not isinstance(candidate, int):
            continue
        if candidate >= 0:
            safe[key] = candidate
    for key in ("input_cost", "output_cost", "total_cost"):
        candidate = value.get(key)
        if isinstance(candidate, bool) or not isinstance(candidate, int | float):
            continue
        if isfinite(candidate) and candidate >= 0:
            safe[key] = float(candidate)
    return safe

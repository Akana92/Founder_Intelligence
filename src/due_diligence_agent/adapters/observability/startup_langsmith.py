from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Final, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from pydantic import BaseModel, ConfigDict, Field

from due_diligence_agent.adapters.observability.langsmith import (
    LangSmithTraceAdapter,
    LangSmithTraceConfig,
)
from due_diligence_agent.adapters.observability.privacy import StrictTraceSanitizer
from due_diligence_agent.ports.tracing import AuditEvent, AuditSpool, TraceSanitizer

_LANGSMITH_STATUS_EVENT: Final[str] = "observability.langsmith_status"
_LANGSMITH_PROVIDER: Final[str] = "langsmith"
_LANGSMITH_INPUT_SCHEMA: Final[str] = "startup_langsmith_input@1"
_LANGSMITH_OUTPUT_SCHEMA: Final[str] = "startup_langsmith_output@1"
_INPUT_KEYS: Final[tuple[str, ...]] = (
    "case_id",
    "run_id",
    "workflow_type",
    "node_name",
    "agent_role",
    "attempt",
    "retry_count",
    "gate",
    "tool",
    "provider",
    "model",
    "request_id",
    "evidence_count",
)
_OUTPUT_KEYS: Final[tuple[str, ...]] = (
    "case_id",
    "run_id",
    "node_name",
    "status",
    "duration_ms",
    "fallback_used",
    "error_code",
    "failure_code",
    "gate",
    "gate_status",
    "report_id",
    "report_revision",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "estimated_cost_usd",
    "cost_usd",
)


class StartupLangSmithTracerConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = False
    credential_present: bool = False
    project_name: str = Field(
        default="dda-queue5-frozen-smoke",
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$",
    )
    flush_timeout_seconds: float = Field(default=5.0, ge=1.0, le=30.0)


class StartupLangSmithNodeTracer:
    def __init__(
        self,
        config: StartupLangSmithTracerConfig,
        *,
        audit_spool: AuditSpool,
        client_factory: Callable[..., object] | None = None,
        sanitizer: TraceSanitizer | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self.audit_spool = audit_spool
        self._sanitizer = sanitizer or StrictTraceSanitizer()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._adapter = LangSmithTraceAdapter(
            LangSmithTraceConfig(
                enabled=config.enabled and config.credential_present,
            ),
            client_factory=client_factory,
            sanitizer=cast(StrictTraceSanitizer, self._sanitizer),
        )
        self._root_ids: dict[tuple[str, str], UUID] = {}
        self._root_dotted_orders: dict[tuple[str, str], str] = {}
        self._identity_by_run: dict[tuple[str, str], dict[str, str]] = {}
        self._closed_runs: set[tuple[str, str]] = set()
        self._degraded_runs: set[tuple[str, str]] = set()
        self._health_by_run: dict[tuple[str, str], str] = {}
        self._usage_by_run: dict[tuple[str, str], dict[str, int | float]] = {}

    def record(self, **attributes: object | None) -> None:
        identity = self._safe_identity(attributes)
        if identity is None:
            return
        run_key = (identity["case_id"], identity["run_id"])
        self._identity_by_run[run_key] = identity

        if not self._config.enabled:
            self._record_health(identity, status="disabled", error_code="tracing_disabled")
            return
        if not self._config.credential_present:
            self._record_health(
                identity,
                status="blocked_missing_credential",
                error_code="missing_credential",
            )
            return
        if run_key in self._degraded_runs:
            return

        try:
            safe = self._sanitizer.sanitize_attributes(attributes)
        except ValueError:
            self._degraded_runs.add(run_key)
            self._record_health(
                identity,
                status="degraded",
                error_code="telemetry_privacy_rejected",
            )
            return

        try:
            self._export_node(run_key, safe)
        except Exception:  # noqa: BLE001 - telemetry export failures must not break workflow
            self._degraded_runs.add(run_key)
            self._record_health(
                identity,
                status="degraded",
                error_code="external_export_failed",
            )
            return
        self._record_health(identity, status="healthy", error_code="none")

    def flush(self) -> None:
        if not self._config.enabled or not self._config.credential_present:
            return
        try:
            client = self._adapter.client
        except Exception:  # noqa: BLE001 - telemetry availability must not break workflow
            for run_key, identity in self._identity_by_run.items():
                self._degraded_runs.add(run_key)
                self._record_health(
                    identity,
                    status="degraded",
                    error_code="external_export_failed",
                )
            return
        if client is None:
            return
        for run_key, root_id in tuple(self._root_ids.items()):
            if run_key in self._closed_runs or run_key in self._degraded_runs:
                continue
            identity = self._identity_by_run[run_key]
            try:
                self._update_run(
                    client,
                    root_id,
                    end_time=self._clock(),
                    outputs=self._root_outputs(run_key, status="flushed"),
                    **self._root_usage_update_kwargs(run_key),
                )
                self._closed_runs.add(run_key)
            except Exception:  # noqa: BLE001 - telemetry export failures must not break workflow
                self._degraded_runs.add(run_key)
                self._record_health(
                    identity,
                    status="degraded",
                    error_code="external_export_failed",
                )
        try:
            self._flush_client(client)
        except Exception:  # noqa: BLE001 - telemetry flush failures must not break workflow
            for run_key, identity in self._identity_by_run.items():
                self._degraded_runs.add(run_key)
                self._record_health(
                    identity,
                    status="degraded",
                    error_code="external_export_failed",
                )

    def _export_node(
        self,
        run_key: tuple[str, str],
        attributes: Mapping[str, str | int | float | bool | None],
    ) -> None:
        client = self._adapter.client
        if client is None:
            return
        node_name = cast(str, attributes["node_name"])
        attempt = int(cast(int | float, attributes.get("attempt") or 1))
        checkpoint_id = str(attributes.get("checkpoint_id") or "none")
        checkpoint_hash = str(attributes.get("checkpoint_hash") or "none")
        ended_at = self._clock()
        duration_ms = max(0.0, float(cast(int | float, attributes.get("duration_ms") or 0)))
        started_at = ended_at - timedelta(milliseconds=duration_ms)
        root_id = self._root_ids.get(run_key)
        if root_id is None:
            root_id = uuid5(NAMESPACE_URL, f"dda-langsmith-root:{run_key[0]}:{run_key[1]}")
            root_dotted_order = _dotted_order_segment(started_at, root_id)
            self._create_run(
                client,
                "startup.workflow",
                root_id,
                trace_id=root_id,
                dotted_order=root_dotted_order,
                start_time=started_at,
                metadata=self._root_metadata(attributes),
                inputs=self._root_inputs(attributes),
            )
            self._root_ids[run_key] = root_id
            self._root_dotted_orders[run_key] = root_dotted_order
        else:
            root_dotted_order = self._root_dotted_orders[run_key]

        child_id = uuid5(
            NAMESPACE_URL,
            (
                f"dda-langsmith-node:{run_key[0]}:{run_key[1]}:"
                f"{node_name}:{attempt}:{checkpoint_id}:{checkpoint_hash}"
            ),
        )
        child_dotted_order = (
            f"{root_dotted_order}.{_dotted_order_segment(started_at, child_id)}"
        )
        self._create_run(
            client,
            f"startup.{node_name}",
            child_id,
            trace_id=root_id,
            dotted_order=child_dotted_order,
            parent_run_id=root_id,
            start_time=started_at,
            metadata=attributes,
            inputs=self._node_inputs(attributes),
            run_type=self._run_type(attributes),
        )
        self._update_run(
            client,
            child_id,
            end_time=ended_at,
            outputs=self._node_outputs(attributes),
        )
        self._record_usage(run_key, attributes)

        if self._is_terminal(attributes):
            self._update_run(
                client,
                root_id,
                end_time=ended_at,
                outputs=self._root_outputs(run_key, status=str(attributes.get("status") or "success")),
                **self._root_usage_update_kwargs(run_key),
            )
            self._closed_runs.add(run_key)
            self._flush_client(client)

    def _create_run(
        self,
        client: object,
        name: str,
        run_id: UUID,
        *,
        trace_id: UUID,
        dotted_order: str,
        metadata: Mapping[str, str | int | float | bool | None],
        inputs: Mapping[str, str | int | float | bool | None],
        run_type: str = "chain",
        parent_run_id: UUID | None = None,
        start_time: datetime | None = None,
    ) -> None:
        method = getattr(client, "create_run")  # noqa: B009 - LangSmith client is optional and dynamically typed
        safe_metadata: dict[str, object] = {
            key: self._safe_summary_value(key, value)
            for key, value in metadata.items()
            if value is not None
        }
        safe_metadata.update(self._langsmith_model_metadata(metadata))
        usage_metadata = self._usage_metadata(metadata)
        if usage_metadata:
            safe_metadata["usage_metadata"] = usage_metadata
        kwargs: dict[str, object] = {
            "id": run_id,
            "trace_id": trace_id,
            "dotted_order": dotted_order,
            "project_name": self._config.project_name,
            "extra": {"metadata": safe_metadata},
            "tags": ["startup", "queue5", "sanitized"],
            "dangerously_allow_filesystem": False,
        }
        kwargs.update(self._usage_kwargs(metadata))
        if parent_run_id is not None:
            kwargs["parent_run_id"] = parent_run_id
        if start_time is not None:
            kwargs["start_time"] = start_time
        method(name, dict(inputs), run_type, **kwargs)

    def _update_run(self, client: object, run_id: UUID, **kwargs: object) -> None:
        method = getattr(client, "update_run")  # noqa: B009 - LangSmith client is optional and dynamically typed
        method(run_id, dangerously_allow_filesystem=False, **kwargs)

    def _flush_client(self, client: object) -> None:
        method = getattr(client, "flush")  # noqa: B009 - LangSmith client is optional and dynamically typed
        method(timeout=self._config.flush_timeout_seconds)

    def _safe_identity(
        self,
        attributes: Mapping[str, object | None],
    ) -> dict[str, str] | None:
        raw = {
            "case_id": attributes.get("case_id"),
            "run_id": attributes.get("run_id"),
            "correlation_id": attributes.get("correlation_id"),
        }
        try:
            safe = self._sanitizer.sanitize_attributes(raw)
        except ValueError:
            return None
        if not all(isinstance(safe.get(key), str) for key in raw):
            return None
        return {key: cast(str, safe[key]) for key in raw}

    def _root_metadata(
        self,
        attributes: Mapping[str, str | int | float | bool | None],
    ) -> dict[str, str | int | float | bool | None]:
        return {
            "case_id": attributes.get("case_id"),
            "run_id": attributes.get("run_id"),
            "correlation_id": attributes.get("correlation_id"),
            "workflow_type": "startup",
            "schema_version": "startup_workflow_span@1",
            "exporter_provider": _LANGSMITH_PROVIDER,
        }

    def _root_inputs(
        self,
        attributes: Mapping[str, str | int | float | bool | None],
    ) -> dict[str, str | int | float | bool | None]:
        return {
            "case_id": attributes.get("case_id"),
            "run_id": attributes.get("run_id"),
            "workflow_type": "startup",
            "schema_version": _LANGSMITH_INPUT_SCHEMA,
        }

    def _node_inputs(
        self,
        attributes: Mapping[str, str | int | float | bool | None],
    ) -> dict[str, str | int | float | bool | None]:
        return self._summary_payload(attributes, _INPUT_KEYS, _LANGSMITH_INPUT_SCHEMA)

    def _node_outputs(
        self,
        attributes: Mapping[str, str | int | float | bool | None],
    ) -> dict[str, str | int | float | bool | None]:
        return self._summary_payload(attributes, _OUTPUT_KEYS, _LANGSMITH_OUTPUT_SCHEMA)

    def _root_outputs(
        self,
        run_key: tuple[str, str],
        *,
        status: str,
    ) -> dict[str, str | int | float | bool | None]:
        identity = self._identity_by_run[run_key]
        outputs: dict[str, str | int | float | bool | None] = {
            "case_id": identity["case_id"],
            "run_id": identity["run_id"],
            "workflow_type": "startup",
            "status": status,
            "schema_version": _LANGSMITH_OUTPUT_SCHEMA,
        }
        outputs.update(self._usage_by_run.get(run_key, {}))
        return outputs

    def _root_usage_update_kwargs(self, run_key: tuple[str, str]) -> dict[str, object]:
        usage = self._usage_by_run.get(run_key)
        if usage is None:
            return {}
        identity = self._identity_by_run[run_key]
        usage_metadata = self._usage_metadata(usage)
        metadata: dict[str, object] = {
            "case_id": identity["case_id"],
            "run_id": identity["run_id"],
            "correlation_id": identity["correlation_id"],
            "workflow_type": "startup",
            "schema_version": "startup_workflow_span@1",
            "exporter_provider": _LANGSMITH_PROVIDER,
        }
        if usage_metadata:
            metadata["usage_metadata"] = usage_metadata
        return {
            **self._usage_kwargs(usage),
            "extra": {"metadata": metadata},
        }

    def _summary_payload(
        self,
        attributes: Mapping[str, str | int | float | bool | None],
        keys: tuple[str, ...],
        schema_version: str,
    ) -> dict[str, str | int | float | bool | None]:
        summary = {
            key: self._safe_summary_value(key, attributes.get(key))
            for key in keys
            if attributes.get(key) is not None
            and (
                key
                not in {
                    "input_tokens",
                    "output_tokens",
                    "total_tokens",
                    "estimated_cost_usd",
                    "cost_usd",
                }
                or self._has_observed_usage(attributes)
            )
        }
        summary["schema_version"] = schema_version
        return summary

    @staticmethod
    def _safe_summary_value(
        key: str,
        value: str | int | float | bool | None,  # noqa: PYI041 - sanitizer preserves integer token counters
    ) -> str | int | float | bool | None:
        if key == "agent_role" and value == "finance":
            return "financial"
        return value

    def _run_type(
        self,
        attributes: Mapping[str, str | int | float | bool | None],
    ) -> str:
        if self._has_observed_usage(attributes) or attributes.get("model") is not None:
            return "llm"
        if attributes.get("tool") is not None:
            return "tool"
        return "chain"

    def _usage_kwargs(
        self,
        attributes: Mapping[str, str | int | float | bool | None],
    ) -> dict[str, int | float]:
        if not self._has_observed_usage(attributes):
            return {}
        kwargs: dict[str, int | float] = {}
        input_tokens = self._positive_int(attributes.get("input_tokens"))
        output_tokens = self._positive_int(attributes.get("output_tokens"))
        total_tokens = self._positive_int(attributes.get("total_tokens"))
        if input_tokens is not None:
            kwargs["prompt_tokens"] = input_tokens
        if output_tokens is not None:
            kwargs["completion_tokens"] = output_tokens
        if total_tokens is not None:
            kwargs["total_tokens"] = total_tokens
        cost = self._cost(attributes)
        if cost is not None:
            kwargs["total_cost"] = cost
        return kwargs

    def _usage_metadata(
        self,
        attributes: Mapping[str, str | int | float | bool | None],
    ) -> dict[str, int | float]:
        if not self._has_observed_usage(attributes):
            return {}
        usage: dict[str, int | float] = {}
        for source_key, target_key in (
            ("input_tokens", "input_tokens"),
            ("output_tokens", "output_tokens"),
            ("total_tokens", "total_tokens"),
        ):
            value = attributes.get(source_key)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                usage[target_key] = value
        cost = self._cost(attributes)
        if cost is not None:
            usage["total_cost"] = cost
        return usage

    def _langsmith_model_metadata(
        self,
        attributes: Mapping[str, str | int | float | bool | None],
    ) -> dict[str, str]:
        provider = attributes.get("provider")
        model = attributes.get("model")
        metadata: dict[str, str] = {}
        if isinstance(provider, str):
            metadata["ls_provider"] = provider
        if isinstance(model, str):
            metadata["ls_model_name"] = model
        return metadata

    def _record_usage(
        self,
        run_key: tuple[str, str],
        attributes: Mapping[str, str | int | float | bool | None],
    ) -> None:
        if not self._has_observed_usage(attributes):
            return
        totals = self._usage_by_run.setdefault(
            run_key,
            {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            },
        )
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            value = self._positive_int(attributes.get(key))
            if value is not None:
                totals[key] = int(totals[key]) + value
        cost = self._cost(attributes)
        if cost is not None:
            cost_key = (
                "cost_usd"
                if self._positive_cost(attributes.get("cost_usd")) is not None
                else "estimated_cost_usd"
            )
            totals[cost_key] = float(totals.get(cost_key, 0.0)) + cost

    def _has_observed_usage(
        self,
        attributes: Mapping[str, str | int | float | bool | None],
    ) -> bool:
        return any(
            self._positive_int(attributes.get(key)) is not None
            for key in ("input_tokens", "output_tokens", "total_tokens")
        ) or self._cost(attributes) is not None

    @staticmethod
    def _positive_int(value: object | None) -> int | None:
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        if value <= 0:
            return None
        return value

    @staticmethod
    def _cost(
        attributes: Mapping[str, str | int | float | bool | None],
    ) -> float | None:
        for key in ("cost_usd", "estimated_cost_usd"):
            value = StartupLangSmithNodeTracer._positive_cost(attributes.get(key))
            if value is not None:
                return value
        return None

    @staticmethod
    def _positive_cost(value: object | None) -> float | None:
        if isinstance(value, bool) or not isinstance(value, int | float):
            return None
        if value <= 0:
            return None
        return float(value)

    def _is_terminal(
        self,
        attributes: Mapping[str, str | int | float | bool | None],
    ) -> bool:
        if attributes.get("status") == "failed":
            return True
        return attributes.get("node_name") == "report" and isinstance(
            attributes.get("report_id"), str
        )

    def _record_health(
        self,
        identity: Mapping[str, str],
        *,
        status: str,
        error_code: str,
    ) -> None:
        run_key = (identity["case_id"], identity["run_id"])
        if self._health_by_run.get(run_key) == status:
            return
        try:
            self.audit_spool.append(
                AuditEvent(
                    schema_version="audit_event@1",
                    event_id=str(uuid4()),
                    timestamp_utc=self._clock().isoformat().replace("+00:00", "Z"),
                    run_id=identity["run_id"],
                    correlation_id=identity["correlation_id"],
                    span_name="analysis.module",
                    event_type=_LANGSMITH_STATUS_EVENT,
                    attributes={
                        "case_id": identity["case_id"],
                        "status": status,
                        "error_code": error_code,
                        "fallback_used": "local_audit",
                        "exporter_provider": _LANGSMITH_PROVIDER,
                    },
                )
            )
        except Exception:  # noqa: BLE001 - local audit fallback must not raise into workflow
            return
        self._health_by_run[run_key] = status


def _dotted_order_segment(start_time: datetime, run_id: UUID) -> str:
    return start_time.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ") + str(run_id)

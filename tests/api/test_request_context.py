from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from starlette.testclient import TestClient

from due_diligence_agent.presentation.api.app import create_app
from due_diligence_agent.presentation.api.context import RequestContext, resolve_request_context


def test_request_context_has_c_ready_nullable_identity_seams_without_trusting_headers() -> None:
    headers = {
        "X-Request-ID": "123e4567-e89b-12d3-a456-426614174000",
        "X-Actor-ID": "founder-123",
        "X-Workspace-ID": "workspace-456",
    }

    context = resolve_request_context(headers)

    assert context == RequestContext(
        request_id=UUID("123e4567-e89b-12d3-a456-426614174000"),
        actor_id=None,
        workspace_id=None,
    )


def test_request_middleware_attaches_safe_trace_attributes_only(monkeypatch) -> None:
    from due_diligence_agent.presentation.api import middleware as api_middleware

    span = _RecordingSpan()
    monkeypatch.setattr(api_middleware.trace, "get_current_span", lambda: span)
    client = TestClient(create_app())

    response = client.get(
        "/api/v1/product/capabilities?document_name=secret_pitch.pdf",
        headers={
            "X-Request-ID": "not-a-uuid",
            "Authorization": "Bearer secret-token",
            "Cookie": "session=secret-cookie",
            "X-Filename": "secret_pitch.pdf",
            "X-Actor-ID": "founder-123",
            "X-Workspace-ID": "workspace-456",
        },
    )

    assert response.status_code == 200
    assert span.name == "http.request"
    assert span.attributes == {
        "http.route": "/api/v1/product/capabilities",
        "http.request.method": "GET",
        "http.response.status_code": 200,
        "api.version": "v1",
        "request_id": response.headers["X-Request-ID"],
    }
    serialized_attrs = repr(span.attributes)
    for forbidden in (
        "secret_pitch.pdf",
        "secret-token",
        "secret-cookie",
        "document_name",
        "founder-123",
        "workspace-456",
    ):
        assert forbidden not in serialized_attrs


def test_unmatched_path_does_not_leak_filename_into_trace(monkeypatch) -> None:
    from due_diligence_agent.presentation.api import middleware as api_middleware

    span = _RecordingSpan()
    monkeypatch.setattr(api_middleware.trace, "get_current_span", lambda: span)
    client = TestClient(create_app())

    response = client.get("/api/v1/uploads/secret_pitch.pdf?document_name=secret_pitch.pdf")

    assert response.status_code == 404
    assert UUID(response.headers["X-Request-ID"])
    assert span.attributes["http.route"] == "unmatched"
    assert span.attributes["api.version"] == "none"
    assert "secret_pitch.pdf" not in repr(span.attributes)


def test_unhandled_error_keeps_request_id_and_safe_trace_metadata(monkeypatch) -> None:
    from due_diligence_agent.presentation.api import middleware as api_middleware

    span = _RecordingSpan()
    monkeypatch.setattr(api_middleware.trace, "get_current_span", lambda: span)
    app = create_app()

    @app.get("/api/v1/test/unhandled")
    def raise_unhandled_error() -> None:
        raise RuntimeError("secret_pitch.pdf must never escape")

    client = TestClient(app, raise_server_exceptions=False)
    request_id = "123e4567-e89b-12d3-a456-426614174000"

    response = client.get(
        "/api/v1/test/unhandled",
        headers={"X-Request-ID": request_id},
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal Server Error"}
    assert response.headers["X-Request-ID"] == request_id
    assert span.attributes == {
        "http.route": "/api/v1/test/unhandled",
        "http.request.method": "GET",
        "http.response.status_code": 500,
        "api.version": "v1",
        "request_id": request_id,
    }
    assert "secret_pitch.pdf" not in repr(span.attributes)


@dataclass
class _RecordingSpan:
    name: str | None = None
    attributes: dict[str, object] = field(default_factory=dict)

    def update_name(self, name: str) -> None:
        self.name = name

    def set_attribute(self, key: str, value: object) -> None:
        self.attributes[key] = value

from __future__ import annotations

import re
from uuid import UUID

from starlette.testclient import TestClient

from due_diligence_agent.application.product.capabilities import ProductCapabilities
from due_diligence_agent.presentation.api.app import create_app


CANONICAL_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def test_health_live_returns_minimal_no_secret_response() -> None:
    client = TestClient(create_app())

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert _is_canonical_uuid(response.headers["X-Request-ID"])
    serialized = response.text.lower()
    for forbidden in ("secret", "token", "api_key", "authorization", "cookie"):
        assert forbidden not in serialized


def test_product_capabilities_route_matches_application_contract() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/product/capabilities")

    assert response.status_code == 200
    contract = ProductCapabilities.model_validate(response.json())
    assert contract.contract_version == "founder_capabilities.v1"
    assert contract.delivery_profile == "sales_ready_hybrid"
    assert contract.user_selectable_modes == ()
    by_key = {capability.key: capability for capability in contract.capabilities}
    assert by_key["public_comparable_analysis"].lifecycle_status == "available"
    assert by_key["universal_upload"].lifecycle_status == "available"


def test_openapi_publishes_versioned_capability_route_and_schema() -> None:
    client = TestClient(create_app())

    schema = client.get("/openapi.json").json()

    assert "/api/v1/product/capabilities" in schema["paths"]
    operation = schema["paths"]["/api/v1/product/capabilities"]["get"]
    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert response_schema["$ref"].endswith("/ProductCapabilities")
    components = schema["components"]["schemas"]
    assert "ProductCapabilities" in components
    assert "Capability" in components


def test_every_response_returns_canonical_request_id() -> None:
    client = TestClient(create_app())
    request_id = "123e4567-e89b-12d3-a456-426614174000"

    response = client.get("/api/v1/product/capabilities", headers={"X-Request-ID": request_id})

    assert response.headers["X-Request-ID"] == request_id
    assert _is_canonical_uuid(response.headers["X-Request-ID"])


def test_malformed_request_id_is_replaced_not_reflected() -> None:
    client = TestClient(create_app())
    malformed = "not-a-uuid-with-secret-filename pitch.pdf"

    response = client.get("/health/live", headers={"X-Request-ID": malformed})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != malformed
    assert _is_canonical_uuid(response.headers["X-Request-ID"])
    assert "pitch.pdf" not in response.headers["X-Request-ID"]


def _is_canonical_uuid(value: str) -> bool:
    return CANONICAL_UUID_RE.match(value) is not None and str(UUID(value)) == value

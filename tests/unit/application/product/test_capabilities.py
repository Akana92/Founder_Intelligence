import pytest
from pydantic import ValidationError

from due_diligence_agent.application.product.capabilities import (
    Capability,
    ProductCapabilitiesService,
)


def test_product_capabilities_contract_is_versioned_and_truthful() -> None:
    capabilities = ProductCapabilitiesService().get_capabilities()

    assert capabilities.contract_version == "founder_capabilities.v1"
    assert capabilities.delivery_profile == "sales_ready_hybrid"
    assert capabilities.research_policy == "guarded_live_with_cached_fallback"
    assert capabilities.surfaces.founder_workspace == "separate_web"
    assert capabilities.surfaces.admin_console == "streamlit"
    assert capabilities.upgrade_target.target == "full_platform"
    assert "analytics_core" in capabilities.upgrade_target.preserved_contracts
    assert "api_v1" in capabilities.upgrade_target.preserved_contracts

    by_key = {capability.key: capability for capability in capabilities.capabilities}

    assert set(by_key) == {
        "universal_upload",
        "primary_startup_analysis",
        "deep_startup_analysis",
        "public_comparable_analysis",
    }
    assert by_key["universal_upload"].lifecycle_status == "available"
    assert by_key["primary_startup_analysis"].lifecycle_status == "available"
    assert by_key["deep_startup_analysis"].lifecycle_status == "planned"
    assert by_key["public_comparable_analysis"].lifecycle_status == "available"
    assert by_key["universal_upload"].label == (
        "Universal startup upload: PDF, DOCX, PNG, JPEG, CSV, XLSX, safe ZIP"
    )
    assert by_key["primary_startup_analysis"].label == (
        "Primary startup profile: deterministic local analysis with guarded live enrichment"
    )

    assert capabilities.user_selectable_modes == ()
    assert all(not capability.user_selectable for capability in capabilities.capabilities)


def test_capability_models_are_frozen_and_forbid_extra_fields() -> None:
    capability = Capability(
        key="universal_upload",
        label="Universal startup document upload",
        lifecycle_status="planned",
        user_selectable=False,
    )

    with pytest.raises(ValidationError):
        capability.lifecycle_status = "available"  # type: ignore[misc]

    with pytest.raises(ValidationError):
        Capability(
            key="unsupported_demo_vertical",
            label="Unsupported demo vertical",
            lifecycle_status="unavailable",
            user_selectable=True,
            unexpected=True,
        )

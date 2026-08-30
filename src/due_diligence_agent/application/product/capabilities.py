"""Framework-independent product capability contract.

This module is consumed by presentation adapters. It must stay independent from
HTTP frameworks, browser UI code, storage adapters, and tracing exporters.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

DeliveryProfile = Literal["sales_ready_hybrid"]
LifecycleStatus = Literal["available", "planned", "unavailable"]
ResearchPolicy = Literal["guarded_live_with_cached_fallback"]
SurfaceKind = Literal["separate_web", "streamlit"]
UpgradeTargetKind = Literal["full_platform"]


class Capability(BaseModel):
    """A truthful product capability exposed to API and UI surfaces."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: Literal[
        "universal_upload",
        "primary_startup_analysis",
        "deep_startup_analysis",
        "public_comparable_analysis",
    ]
    label: str
    lifecycle_status: LifecycleStatus
    user_selectable: bool = False


class ProductSurfaces(BaseModel):
    """Product surface ownership for delivery profile B."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    founder_workspace: SurfaceKind
    admin_console: SurfaceKind


class UpgradeTarget(BaseModel):
    """Forward-compatible C upgrade seam."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    target: UpgradeTargetKind
    preserved_contracts: tuple[str, ...]


class ProductCapabilities(BaseModel):
    """Versioned capabilities contract for Founder Launch Intelligence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_version: Literal["founder_capabilities.v1"]
    delivery_profile: DeliveryProfile
    capabilities: tuple[Capability, ...]
    research_policy: ResearchPolicy
    surfaces: ProductSurfaces
    upgrade_target: UpgradeTarget
    user_selectable_modes: tuple[()] = ()


class ProductCapabilitiesService:
    """Returns the current truthful delivery-profile capability contract."""

    def get_capabilities(self) -> ProductCapabilities:
        return ProductCapabilities(
            contract_version="founder_capabilities.v1",
            delivery_profile="sales_ready_hybrid",
            capabilities=(
                Capability(
                    key="universal_upload",
                    label="Universal startup upload: PDF, DOCX, PNG, JPEG, CSV, XLSX, safe ZIP",
                    lifecycle_status="available",
                ),
                Capability(
                    key="primary_startup_analysis",
                    label=(
                        "Primary startup profile: deterministic local analysis with guarded "
                        "live enrichment"
                    ),
                    lifecycle_status="available",
                ),
                Capability(
                    key="deep_startup_analysis",
                    label="Deep startup market and evidence analysis",
                    lifecycle_status="planned",
                ),
                Capability(
                    key="public_comparable_analysis",
                    label="Public company comparable analysis",
                    lifecycle_status="available",
                ),
            ),
            research_policy="guarded_live_with_cached_fallback",
            surfaces=ProductSurfaces(
                founder_workspace="separate_web",
                admin_console="streamlit",
            ),
            upgrade_target=UpgradeTarget(
                target="full_platform",
                preserved_contracts=("analytics_core", "api_v1"),
            ),
        )

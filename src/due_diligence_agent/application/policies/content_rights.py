from enum import StrEnum


class LicenseClass(StrEnum):
    DISCOVERY_METADATA_ONLY = "discovery_metadata_only"
    RESEARCH_ONLY = "research_only"
    PUBLIC_PRIMARY = "public_primary"
    RIGHTS_CLEARED_FULL_TEXT = "rights_cleared_full_text"


def may_store_full_text(license_class: LicenseClass | str) -> bool:
    return LicenseClass(license_class) is LicenseClass.RIGHTS_CLEARED_FULL_TEXT

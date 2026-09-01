"""Version-advisory LiquiGen host compatibility contract."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .runtime import RuntimeBinding

TESTED_LIQUIGEN_VERSIONS = ("1.0.5",)
RECOMMENDED_LIQUIGEN_VERSION = "1.7.1"
BASE_INTERFACES = frozenset({"liquigen.window.v1", "liquigen.project.read.v1"})


def assess_compatibility(
    binding: RuntimeBinding,
    *,
    interfaces: Iterable[str],
) -> dict[str, object]:
    """Assess a host by stable identity and named interfaces, never an EXE hash."""

    available = frozenset(str(item).strip() for item in interfaces if str(item).strip())
    executable_name_matches = Path(binding.executable).name.casefold() == "liquigen.exe"
    missing = sorted(BASE_INTERFACES - available)
    compatible = executable_name_matches and not missing
    tested = binding.version in TESTED_LIQUIGEN_VERSIONS
    if not compatible:
        status = "unsupported_host_interface"
    elif tested:
        status = "compatible_tested"
    else:
        status = "compatible_untested"
    report: dict[str, object] = {
        "compatible": compatible,
        "status": status,
        "host_match": {
            "executable_names": ["LiquiGen.exe"],
            "executable_name_matches": executable_name_matches,
            "executable_hash_required": False,
            "matched_by": ["executable_name", "interfaces"],
            "version_policy": "advisory_only",
        },
        "interfaces": {
            "required": sorted(BASE_INTERFACES),
            "available": sorted(available),
            "missing": missing,
        },
        "version": {
            "detected": binding.version,
            "tested": tested,
            "tested_versions": list(TESTED_LIQUIGEN_VERSIONS),
        },
        "recommendation": {
            "liquigen_version": RECOMMENDED_LIQUIGEN_VERSION,
            "message": (
                "Install the recommended LiquiGen version only if an interface probe fails."
            ),
        },
    }
    if not compatible:
        report["failure"] = {
            "code": "unsupported_host_interface",
            "missing_interfaces": missing,
            "install_liquigen_version": RECOMMENDED_LIQUIGEN_VERSION,
        }
    return report


__all__ = [
    "BASE_INTERFACES",
    "RECOMMENDED_LIQUIGEN_VERSION",
    "TESTED_LIQUIGEN_VERSIONS",
    "assess_compatibility",
]

from dcc_mcp_liquigen.compatibility import assess_compatibility
from dcc_mcp_liquigen.runtime import RuntimeBinding


def test_untested_liquigen_version_is_accepted_when_name_and_interfaces_match():
    binding = RuntimeBinding(
        pid=42,
        window_handle=84,
        executable="C:/Program Files/JangaFX/LiquiGen/LiquiGen.exe",
        version="1.9.0",
    )

    report = assess_compatibility(
        binding,
        interfaces={"liquigen.window.v1", "liquigen.project.read.v1"},
    )

    assert report["compatible"] is True
    assert report["status"] == "compatible_untested"
    assert report["host_match"]["executable_hash_required"] is False
    assert report["host_match"]["matched_by"] == ["executable_name", "interfaces"]
    assert report["recommendation"]["liquigen_version"] == "1.7.1"


def test_missing_interface_reports_the_version_to_install():
    binding = RuntimeBinding(
        pid=42,
        window_handle=84,
        executable="C:/Program Files/JangaFX/LiquiGen/LiquiGen.exe",
        version="2.0.0",
    )

    report = assess_compatibility(binding, interfaces={"liquigen.window.v1"})

    assert report["compatible"] is False
    assert report["failure"] == {
        "code": "unsupported_host_interface",
        "missing_interfaces": ["liquigen.project.read.v1"],
        "install_liquigen_version": "1.7.1",
    }


def test_current_liquigen_release_is_advisory_until_live_acceptance():
    binding = RuntimeBinding(
        pid=42,
        window_handle=84,
        executable="C:/Program Files/JangaFX/LiquiGen/LiquiGen.exe",
        version="1.7.1",
    )

    report = assess_compatibility(
        binding,
        interfaces={"liquigen.window.v1", "liquigen.project.read.v1"},
    )

    assert report["compatible"] is True
    assert report["status"] == "compatible_untested"
    assert report["version"]["tested_versions"] == ["1.0.5"]
    assert report["recommendation"]["liquigen_version"] == "1.7.1"

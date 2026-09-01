import json
import zipfile
from pathlib import Path

from dcc_mcp_liquigen.packaging import build_local_native_bundle, build_public_bundle

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_installer_retries_transient_windows_launcher_lock():
    installer = (PROJECT_ROOT / "packaging" / "install.ps1").read_text(encoding="utf-8")

    assert "$maxInstallAttempts = 3" in installer
    assert "Start-Sleep -Milliseconds" in installer
    assert "vx uv tool install failed after" in installer
    assert "foreach ($checksumLine in $checksumLines)" in installer
    assert "dcc_mcp_liquigen_command_client.exe" in installer


def test_public_bundle_contains_only_external_adapter_payload(tmp_path: Path):
    project = tmp_path / "project"
    wheel = project / "dist" / "dcc_mcp_liquigen-0.1.0-py3-none-any.whl"
    wheel.parent.mkdir(parents=True)
    wheel.write_bytes(b"wheel")
    (project / "packaging").mkdir()
    (project / "packaging" / "install.ps1").write_text("# installer\n", encoding="utf-8")
    (project / "docs").mkdir()
    (project / "docs" / "distribution.md").write_text("distribution\n", encoding="utf-8")
    (project / "LICENSE").write_text("MIT\n", encoding="utf-8")
    receiver = project / "examples" / "ue58_receiver"
    receiver.mkdir(parents=True)
    (receiver / "import_flipbook.py").write_text("# receiver\n", encoding="utf-8")
    showcase_skill = project / "skills" / "unreal-liquigen-showcase"
    (showcase_skill / "scripts").mkdir(parents=True)
    (showcase_skill / "SKILL.md").write_text("# Unreal skill\n", encoding="utf-8")
    (showcase_skill / "tools.yaml").write_text("tools: []\n", encoding="utf-8")
    (showcase_skill / "scripts" / "import_vat_bundle.py").write_text(
        "# VAT receiver\n", encoding="utf-8"
    )

    artifacts = build_public_bundle(project, tmp_path / "release", wheel, "0.1.0")

    with zipfile.ZipFile(artifacts.bundle) as archive:
        names = archive.namelist()
        manifest = json.loads(archive.read("manifest.json"))
        assert "payload/dcc_mcp_liquigen-0.1.0-py3-none-any.whl" in names
        assert "install.ps1" in names
        assert "README-DISTRIBUTION.md" in names
        assert "SHA256SUMS" in names
        assert "ue58_receiver/import_flipbook.py" in names
        assert "ue58_receiver/skills/unreal-liquigen-showcase/SKILL.md" in names
        assert "ue58_receiver/skills/unreal-liquigen-showcase/tools.yaml" in names
        assert "ue58_receiver/skills/unreal-liquigen-showcase/scripts/import_vat_bundle.py" in names
        assert not any(name.startswith("native/") for name in names)
        assert not any("research-notes" in name for name in names)
        assert manifest["host_match"]["executable_hash_required"] is False
        assert manifest["host_match"]["version_policy"] == "advisory_only"
        assert manifest["host_match"]["tested_versions"] == ["1.0.5"]
        assert manifest["host_match"]["recommended_version"] == "1.7.1"
        assert manifest["distribution"]["includes_injection_payload"] is False
        assert manifest["distribution"]["includes_liquigen_binaries"] is False
        assert manifest["distribution"]["ue58_skill"] == (
            "ue58_receiver/skills/unreal-liquigen-showcase/SKILL.md"
        )
        assert manifest["bridge_capabilities"] == [
            "exact_host_binding",
            "preset_discovery",
            "safe_project_staging",
            "project_binary_inspection",
            "node_schema_discovery",
            "project_graph_transaction",
            "replayable_node_recipe",
            "export_bundle_validation",
            "accessible_companion_menu",
        ]
        assert manifest["unreal_handoff"]["default"] == "ue_vat"
        assert manifest["unreal_handoff"]["vdb_role"] == "velocity_field_auxiliary"
    assert artifacts.bundle_checksum.is_file()


def test_local_native_bundle_is_explicit_and_checksums_both_bridge_files(tmp_path: Path):
    project = tmp_path / "project"
    wheel = project / "dist" / "dcc_mcp_liquigen-0.1.0-py3-none-any.whl"
    wheel.parent.mkdir(parents=True)
    wheel.write_bytes(b"wheel")
    (project / "packaging").mkdir()
    (project / "packaging" / "install.ps1").write_text("# installer\n", encoding="utf-8")
    (project / "docs").mkdir()
    (project / "docs" / "distribution.md").write_text("distribution\n", encoding="utf-8")
    (project / "LICENSE").write_text("MIT\n", encoding="utf-8")
    receiver = project / "examples" / "ue58_receiver"
    receiver.mkdir(parents=True)
    (receiver / "README.md").write_text("receiver\n", encoding="utf-8")
    showcase_skill = project / "skills" / "unreal-liquigen-showcase"
    showcase_skill.mkdir(parents=True)
    (showcase_skill / "SKILL.md").write_text("skill\n", encoding="utf-8")
    native = project / ".artifacts" / "liquigen-command-bridge-build" / "Release"
    native.mkdir(parents=True)
    (native / "dcc_mcp_liquigen_command_client.exe").write_bytes(b"client")
    (native / "dcc_mcp_liquigen_command_hook.dll").write_bytes(b"hook")

    artifacts = build_local_native_bundle(
        project, tmp_path / "release", wheel, "0.1.0", native_bridge_dir=native
    )

    assert "local-native" in artifacts.bundle.name
    with zipfile.ZipFile(artifacts.bundle) as archive:
        names = archive.namelist()
        manifest = json.loads(archive.read("manifest.json"))
        sums = archive.read("SHA256SUMS").decode("ascii").splitlines()
        assert "native/dcc_mcp_liquigen_command_client.exe" in names
        assert "native/dcc_mcp_liquigen_command_hook.dll" in names
        assert len(sums) == 3
        assert manifest["distribution"]["includes_injection_payload"] is True
        assert manifest["interface_contract"]["host_command_bridge_abi"] == 2
        assert manifest["interface_contract"]["host_command_bridge_included"] is True
        assert "fresh_export_workflow" in manifest["bridge_capabilities"]
        assert manifest["distribution"]["includes_liquigen_binaries"] is False

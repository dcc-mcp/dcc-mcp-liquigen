"""Build the public, external-only LiquiGen adapter distribution bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from .__version__ import __version__
from .compatibility import (
    BASE_INTERFACES,
    RECOMMENDED_LIQUIGEN_VERSION,
    TESTED_LIQUIGEN_VERSIONS,
)

_ZIP_TIMESTAMP = (2020, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class ReleaseArtifacts:
    bundle: Path
    bundle_checksum: Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_bytes(archive: zipfile.ZipFile, name: str, payload: bytes) -> None:
    info = zipfile.ZipInfo(name, _ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, payload)


def _manifest(
    version: str, wheel: Path, *, includes_native_bridge: bool = False
) -> dict[str, object]:
    capabilities = [
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
    if includes_native_bridge:
        capabilities.extend(
            [
                "semantic_host_commands",
                "native_project_loader",
                "fresh_export_workflow",
            ]
        )
    return {
        "schema_version": 1,
        "name": "dcc-mcp-liquigen",
        "version": version,
        "host_match": {
            "executable_names": ["LiquiGen.exe"],
            "executable_hash_required": False,
            "version_policy": "advisory_only",
            "tested_versions": list(TESTED_LIQUIGEN_VERSIONS),
            "recommended_version": RECOMMENDED_LIQUIGEN_VERSION,
        },
        "interface_contract": {
            "required": sorted(BASE_INTERFACES),
            "semantic_ui_bridge_abi": 1,
            "semantic_ui_bridge_optional": True,
            "host_command_bridge_abi": 2,
            "host_command_bridge_included": includes_native_bridge,
        },
        "bridge_capabilities": capabilities,
        "unreal_handoff": {
            "default": "ue_vat",
            "runtime_surface": "ue_vat",
            "cinematic_surface": "alembic",
            "billboard_fallback": "flipbook",
            "vdb_role": "velocity_field_auxiliary",
            "runtime_acceptance_required": True,
        },
        "payload": {
            "wheel": f"payload/{wheel.name}",
            "wheel_sha256": _sha256(wheel),
        },
        "distribution": {
            "kind": "external_adapter",
            "ue58_receiver": "ue58_receiver/LiquiGenUE58.uproject",
            "ue58_skill": "ue58_receiver/skills/unreal-liquigen-showcase/SKILL.md",
            "includes_injection_payload": includes_native_bridge,
            "includes_liquigen_binaries": False,
            "includes_liquigen_presets": False,
        },
    }


def _native_bridge_payloads(native_bridge_dir: Path) -> dict[str, Path]:
    source = native_bridge_dir.resolve(strict=True)
    payloads = {
        "native/dcc_mcp_liquigen_command_client.exe": (
            source / "dcc_mcp_liquigen_command_client.exe"
        ),
        "native/dcc_mcp_liquigen_command_hook.dll": (source / "dcc_mcp_liquigen_command_hook.dll"),
    }
    for path in payloads.values():
        path.resolve(strict=True)
        if not path.is_file() or path.stat().st_size <= 0:
            raise ValueError("native command bridge payload is missing or empty")
    return payloads


def _build_bundle(
    project_root: Path,
    output_dir: Path,
    wheel: Path,
    version: str,
    *,
    native_bridge_dir: Optional[Path] = None,
) -> ReleaseArtifacts:
    """Create one reproducible external-only or explicit local-native ZIP."""

    root = project_root.resolve(strict=True)
    wheel = wheel.resolve(strict=True)
    output = output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    required = {
        "install.ps1": root / "packaging" / "install.ps1",
        "README-DISTRIBUTION.md": root / "docs" / "distribution.md",
        "LICENSE": root / "LICENSE",
    }
    for path in required.values():
        path.resolve(strict=True)
    receiver_root = (root / "examples" / "ue58_receiver").resolve(strict=True)
    receiver_files = sorted(
        path
        for path in receiver_root.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix.casefold() in {".ini", ".md", ".py", ".uproject"}
    )
    showcase_skill_root = (root / "skills" / "unreal-liquigen-showcase").resolve(strict=True)
    showcase_skill_files = sorted(
        path
        for path in showcase_skill_root.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix.casefold() in {".md", ".py", ".yaml"}
    )
    native_payloads = _native_bridge_payloads(native_bridge_dir) if native_bridge_dir else {}

    qualifier = "local-native-" if native_payloads else ""
    bundle = output / f"dcc-mcp-liquigen-{version}-{qualifier}windows-x64.zip"
    manifest = _manifest(version, wheel, includes_native_bridge=bool(native_payloads))
    if native_payloads:
        manifest["payload"]["native"] = {
            name: _sha256(path) for name, path in native_payloads.items()
        }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    checksum_entries = [(f"payload/{wheel.name}", _sha256(wheel))]
    checksum_entries.extend((name, _sha256(path)) for name, path in native_payloads.items())
    sums = "".join(f"{digest}  {name}\n" for name, digest in checksum_entries).encode()
    with zipfile.ZipFile(bundle, "w") as archive:
        _write_bytes(archive, "LICENSE", required["LICENSE"].read_bytes())
        _write_bytes(
            archive,
            "README-DISTRIBUTION.md",
            required["README-DISTRIBUTION.md"].read_bytes(),
        )
        _write_bytes(archive, "SHA256SUMS", sums)
        _write_bytes(archive, "install.ps1", required["install.ps1"].read_bytes())
        _write_bytes(archive, "manifest.json", manifest_bytes)
        _write_bytes(archive, f"payload/{wheel.name}", wheel.read_bytes())
        for name, path in native_payloads.items():
            _write_bytes(archive, name, path.read_bytes())
        for path in receiver_files:
            name = "ue58_receiver/" + path.relative_to(receiver_root).as_posix()
            _write_bytes(archive, name, path.read_bytes())
        for path in showcase_skill_files:
            relative = path.relative_to(showcase_skill_root).as_posix()
            name = f"ue58_receiver/skills/unreal-liquigen-showcase/{relative}"
            _write_bytes(archive, name, path.read_bytes())
    checksum = output / f"{bundle.name}.sha256"
    checksum.write_text(f"{_sha256(bundle)}  {bundle.name}\n", encoding="ascii")
    return ReleaseArtifacts(bundle=bundle, bundle_checksum=checksum)


def build_public_bundle(
    project_root: Path,
    output_dir: Path,
    wheel: Path,
    version: str,
) -> ReleaseArtifacts:
    """Create a reproducible ZIP without proprietary or injection payloads."""

    return _build_bundle(project_root, output_dir, wheel, version)


def build_local_native_bundle(
    project_root: Path,
    output_dir: Path,
    wheel: Path,
    version: str,
    native_bridge_dir: Optional[Path] = None,
) -> ReleaseArtifacts:
    """Create a local-evaluation ZIP with the original native command bridge."""

    bridge = native_bridge_dir or (
        project_root / ".artifacts" / "liquigen-command-bridge-build" / "Release"
    )
    return _build_bundle(
        project_root,
        output_dir,
        wheel,
        version,
        native_bridge_dir=bridge,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, default=Path("dist"))
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--version", default=__version__)
    parser.add_argument("--include-native-bridge", action="store_true")
    parser.add_argument("--native-bridge-dir", type=Path)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    root = args.project_root.resolve(strict=True)
    wheel = args.wheel or root / "dist" / f"dcc_mcp_liquigen-{args.version}-py3-none-any.whl"
    if args.include_native_bridge:
        artifacts = build_local_native_bundle(
            root,
            args.output_dir,
            wheel,
            args.version,
            native_bridge_dir=args.native_bridge_dir,
        )
    else:
        artifacts = build_public_bundle(root, args.output_dir, wheel, args.version)
    print(
        json.dumps(
            {
                "success": True,
                "bundle": str(artifacts.bundle),
                "bundle_checksum": str(artifacts.bundle_checksum),
            },
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()


__all__ = [
    "ReleaseArtifacts",
    "build_local_native_bundle",
    "build_public_bundle",
    "main",
]

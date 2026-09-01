"""Stage a canonical LiquiGen dynamic-remeshing VAT bundle in UE 5.8."""

from __future__ import annotations

from pathlib import Path

from _showcase_common import asset_prefix as validate_prefix
from _showcase_common import game_asset_path
from _vat_receiver import canonical_vat_bundle, import_vat_assets
from dcc_mcp_core.skill import skill_entry, skill_error, skill_success


@skill_entry
def import_vat_bundle(
    source_directory: str,
    destination: str,
    asset_prefix: str,
    source_kind: str = "liquigen_export",
    **_kwargs,
) -> dict:
    try:
        import unreal

        source = Path(source_directory)
        if not source.is_absolute():
            raise ValueError("source_directory must be absolute")
        if source_kind != "liquigen_export":
            raise ValueError("VAT import accepts only source_kind=liquigen_export")
        destination = game_asset_path(destination)
        prefix = validate_prefix(asset_prefix)
        bundle = canonical_vat_bundle(source)
        result = import_vat_assets(unreal, bundle, destination, prefix)
        return skill_success(
            "Staged canonical LiquiGen fluid VAT bundle in Unreal Engine 5.8",
            source_directory=str(bundle["source"]),
            source_kind=source_kind,
            **result,
            prompt=(
                "Call unreal_liquigen_showcase__finalize_vat_bundle with the same source, "
                "destination, prefix, and source kind after this tool returns."
            ),
        )
    except Exception as exc:
        return skill_error(
            "Failed to stage LiquiGen VAT bundle",
            str(exc),
            possible_solutions=[
                "Export FBX, lookup EXR, position EXR, rotation EXR, and *_info.json together.",
                "Install and enable the SideFX Labs UE 5.8 content plugin.",
                "Choose a new /Game destination or asset_prefix.",
            ],
        )


def main(**kwargs) -> dict:
    return import_vat_bundle(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)

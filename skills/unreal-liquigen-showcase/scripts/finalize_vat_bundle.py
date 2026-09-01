"""Finalize one staged LiquiGen dynamic-remeshing VAT bundle in UE 5.8."""

from __future__ import annotations

from pathlib import Path

from _showcase_common import asset_prefix as validate_prefix
from _showcase_common import game_asset_path
from _vat_receiver import canonical_vat_bundle, finalize_vat_assets
from dcc_mcp_core.skill import skill_entry, skill_error, skill_success


@skill_entry
def finalize_vat_bundle(
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
            raise ValueError("VAT finalization accepts only source_kind=liquigen_export")
        destination = game_asset_path(destination)
        prefix = validate_prefix(asset_prefix)
        bundle = canonical_vat_bundle(source)
        result = finalize_vat_assets(unreal, bundle, destination, prefix)
        return skill_success(
            "Finalized canonical LiquiGen fluid VAT bundle in Unreal Engine 5.8",
            source_directory=str(bundle["source"]),
            source_kind=source_kind,
            **result,
            prompt="Stage the finalized mesh and material instance in the showcase level.",
        )
    except Exception as exc:
        return skill_error(
            "Failed to finalize LiquiGen VAT bundle",
            str(exc),
            possible_solutions=[
                "Call import_vat_bundle first with exactly the same arguments.",
                "Allow the import call to return before finalizing so Unreal advances one tick.",
                "Verify all six staged assets remain under the requested /Game destination.",
            ],
        )


def main(**kwargs) -> dict:
    return finalize_vat_bundle(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)

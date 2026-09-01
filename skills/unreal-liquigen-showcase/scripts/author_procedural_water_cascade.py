"""Author an Unreal-native water cascade with explicit LiquiGen provenance."""

from __future__ import annotations

from pathlib import Path

from _receiver import create_procedural_material, create_procedural_water_system
from _showcase_common import asset_prefix as validate_prefix
from _showcase_common import blast_diameter as validate_splash_diameter
from _showcase_common import chain_config, game_asset_path
from _vat_receiver import canonical_vat_bundle
from dcc_mcp_core.skill import skill_entry, skill_error, skill_success


@skill_entry
def author_procedural_water_cascade(
    source_project: str,
    source_directory: str,
    destination: str,
    asset_prefix: str,
    chain_count: int = 5,
    delay_seconds: float = 0.18,
    spacing_cm: float = 230.0,
    vertical_drop_cm: float = 140.0,
    splash_diameter_cm: float = 360.0,
    particle_count: int = 30,
    **_kwargs,
) -> dict:
    try:
        import unreal

        project = Path(source_project)
        if not project.is_absolute():
            raise ValueError("source_project must be absolute")
        project = project.resolve(strict=True)
        if not project.is_file() or project.suffix.casefold() != ".liquigen":
            raise ValueError("source_project must be an existing .liquigen project")
        export_directory = Path(source_directory)
        if not export_directory.is_absolute():
            raise ValueError("source_directory must be absolute")
        bundle = canonical_vat_bundle(export_directory)
        destination = game_asset_path(destination)
        prefix = validate_prefix(asset_prefix)
        chain = chain_config(chain_count, delay_seconds, spacing_cm)
        splash_diameter_cm = validate_splash_diameter(splash_diameter_cm)
        vertical_drop_cm = float(vertical_drop_cm)
        if not 25.0 <= vertical_drop_cm <= 2000.0:
            raise ValueError("vertical_drop_cm must be between 25 and 2000")
        particle_count = int(particle_count)
        if not 4 <= particle_count <= 128:
            raise ValueError("particle_count must be between 4 and 128")

        names = {
            "sheet": f"M_{prefix}_Sheet",
            "foam": f"M_{prefix}_Foam",
            "droplets": f"M_{prefix}_Droplets",
            "niagara": f"NS_{prefix}",
        }
        paths = {key: f"{destination}/{name}" for key, name in names.items()}
        existing = [
            path for path in paths.values() if unreal.EditorAssetLibrary.does_asset_exist(path)
        ]
        if existing:
            raise RuntimeError("destination assets already exist: " + ", ".join(existing))
        unreal.EditorAssetLibrary.make_directory(destination)

        materials = {
            "sheet": create_procedural_material(
                unreal, destination, names["sheet"], (0.02, 0.20, 0.52), 0.36
            ),
            "foam": create_procedural_material(
                unreal, destination, names["foam"], (0.28, 0.62, 0.92), 0.48
            ),
            "droplets": create_procedural_material(
                unreal, destination, names["droplets"], (0.03, 0.36, 0.82), 0.58
            ),
        }
        system = create_procedural_water_system(
            unreal,
            materials,
            destination,
            names["niagara"],
            chain,
            splash_diameter_cm,
            particle_count,
            vertical_drop_cm,
        )
        source_kind = "liquigen_export"
        for asset in (*materials.values(), system):
            unreal.EditorAssetLibrary.set_metadata_tag(asset, "LiquiGen.SourceKind", source_kind)
            unreal.EditorAssetLibrary.set_metadata_tag(
                asset, "LiquiGen.SourceProject", str(project)
            )
            unreal.EditorAssetLibrary.set_metadata_tag(
                asset, "LiquiGen.SourceDirectory", str(bundle["source"])
            )
            unreal.EditorAssetLibrary.set_metadata_tag(
                asset, "LiquiGen.Appearance", "unreal_procedural_water"
            )
            unreal.EditorAssetLibrary.set_metadata_tag(
                asset, "LiquiGen.SourceFrameCount", str(bundle["frame_count"])
            )
            unreal.EditorAssetLibrary.set_metadata_tag(
                asset, "LiquiGen.SplashDiameterCm", str(splash_diameter_cm)
            )
            unreal.EditorAssetLibrary.set_metadata_tag(
                asset,
                "LiquiGen.CascadeTiming",
                (
                    f"count={chain['count']};delay={chain['delay_seconds']};"
                    f"spacing={chain['spacing_cm']};drop={vertical_drop_cm}"
                ),
            )
            unreal.EditorAssetLibrary.save_loaded_asset(asset, only_if_is_dirty=False)

        verified = {key: unreal.EditorAssetLibrary.load_asset(path) for key, path in paths.items()}
        if any(asset is None for asset in verified.values()):
            raise RuntimeError("procedural water assets failed asset-registry readback")
        return skill_success(
            "Authored Unreal-procedural water cascade from LiquiGen timing and provenance",
            source_project=str(project),
            source_directory=str(bundle["source"]),
            source_kind=source_kind,
            appearance="unreal_procedural_water",
            vat_frame_count=bundle["frame_count"],
            vat_source_fps=bundle["source_fps"],
            chain=chain,
            vertical_drop_cm=vertical_drop_cm,
            splash_diameter_cm=splash_diameter_cm,
            particle_count_per_sheet_layer=particle_count,
            material_paths={key: paths[key] for key in materials},
            niagara_path=paths["niagara"],
            emitter_count=int(chain["count"]) * 3,
            verified_classes={key: asset.get_class().get_name() for key, asset in verified.items()},
            prompt="Stage the returned niagara_path with stage_water_cascade.",
        )
    except Exception as exc:
        return skill_error(
            "Failed to author procedural LiquiGen water cascade",
            str(exc),
            possible_solutions=[
                "Use an absolute .liquigen project and its canonical VAT export directory.",
                "Choose a new /Game destination or asset_prefix.",
            ],
        )


def main(**kwargs) -> dict:
    return author_procedural_water_cascade(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)

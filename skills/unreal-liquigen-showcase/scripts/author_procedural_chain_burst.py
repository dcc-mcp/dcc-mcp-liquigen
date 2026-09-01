"""Author an Unreal-native Niagara chain burst with explicit LiquiGen provenance."""

from __future__ import annotations

from pathlib import Path

from _receiver import create_procedural_chain_system, create_procedural_material
from _showcase_common import asset_prefix as validate_prefix
from _showcase_common import blast_diameter as validate_blast_diameter
from _showcase_common import chain_config, game_asset_path
from dcc_mcp_core.skill import skill_entry, skill_error, skill_success


def _source_bundle(source_directory: Path) -> dict[str, list[str]]:
    files = [item for item in source_directory.iterdir() if item.is_file()]
    bundle = {
        "fbx": sorted(str(item) for item in files if item.suffix.casefold() == ".fbx"),
        "exr": sorted(str(item) for item in files if item.suffix.casefold() == ".exr"),
        "json": sorted(str(item) for item in files if item.suffix.casefold() == ".json"),
    }
    if not bundle["fbx"] or len(bundle["exr"]) < 3 or not bundle["json"]:
        raise ValueError("source_directory is not a canonical LiquiGen VAT export bundle")
    return bundle


@skill_entry
def author_procedural_chain_burst(
    source_project: str,
    source_directory: str,
    destination: str,
    asset_prefix: str,
    chain_count: int = 5,
    delay_seconds: float = 0.18,
    spacing_cm: float = 260.0,
    blast_diameter_cm: float = 600.0,
    particle_count: int = 28,
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
        export_directory = export_directory.resolve(strict=True)
        if not export_directory.is_dir():
            raise ValueError("source_directory must be an existing directory")
        bundle = _source_bundle(export_directory)
        destination = game_asset_path(destination)
        prefix = validate_prefix(asset_prefix)
        chain = chain_config(chain_count, delay_seconds, spacing_cm)
        blast_diameter_cm = validate_blast_diameter(blast_diameter_cm)
        particle_count = int(particle_count)
        if not 4 <= particle_count <= 128:
            raise ValueError("particle_count must be between 4 and 128")

        names = {
            "core": f"M_{prefix}_Core",
            "plume": f"M_{prefix}_Plume",
            "sparks": f"M_{prefix}_Sparks",
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
            "core": create_procedural_material(
                unreal, destination, names["core"], (18.0, 2.4, 0.08), 0.95
            ),
            "plume": create_procedural_material(
                unreal, destination, names["plume"], (5.2, 0.36, 0.025), 0.62
            ),
            "sparks": create_procedural_material(
                unreal, destination, names["sparks"], (28.0, 8.0, 0.35), 1.0
            ),
        }
        system = create_procedural_chain_system(
            unreal,
            materials,
            destination,
            names["niagara"],
            chain,
            blast_diameter_cm,
            particle_count,
        )
        source_kind = "liquigen_export"
        for asset in (*materials.values(), system):
            unreal.EditorAssetLibrary.set_metadata_tag(asset, "LiquiGen.SourceKind", source_kind)
            unreal.EditorAssetLibrary.set_metadata_tag(
                asset, "LiquiGen.SourceProject", str(project)
            )
            unreal.EditorAssetLibrary.set_metadata_tag(
                asset, "LiquiGen.SourceDirectory", str(export_directory)
            )
            unreal.EditorAssetLibrary.set_metadata_tag(
                asset, "LiquiGen.Appearance", "unreal_procedural"
            )
            unreal.EditorAssetLibrary.set_metadata_tag(
                asset, "LiquiGen.BlastDiameterCm", str(blast_diameter_cm)
            )
            unreal.EditorAssetLibrary.set_metadata_tag(
                asset,
                "LiquiGen.ChainTiming",
                f"count={chain['count']};delay={chain['delay_seconds']};spacing={chain['spacing_cm']}",
            )
            unreal.EditorAssetLibrary.save_loaded_asset(asset, only_if_is_dirty=False)

        verified = {key: unreal.EditorAssetLibrary.load_asset(path) for key, path in paths.items()}
        if any(asset is None for asset in verified.values()):
            raise RuntimeError("procedural assets failed asset-registry readback")
        return skill_success(
            "Authored Unreal-procedural chain burst from LiquiGen timing and provenance",
            source_project=str(project),
            source_directory=str(export_directory),
            source_kind=source_kind,
            appearance="unreal_procedural",
            bundle_inventory={key: len(value) for key, value in bundle.items()},
            chain=chain,
            blast_diameter_cm=blast_diameter_cm,
            particle_count_per_core_layer=particle_count,
            material_paths={key: paths[key] for key in materials},
            niagara_path=paths["niagara"],
            emitter_count=int(chain["count"]) * 3,
            verified_classes={key: asset.get_class().get_name() for key, asset in verified.items()},
            prompt="Stage the returned niagara_path with stage_chain_burst.",
        )
    except Exception as exc:
        return skill_error(
            "Failed to author procedural LiquiGen chain burst",
            str(exc),
            possible_solutions=[
                "Use an absolute .liquigen project and its canonical VAT export directory.",
                "Choose a new /Game destination or asset_prefix.",
            ],
        )


def main(**kwargs) -> dict:
    return author_procedural_chain_burst(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)

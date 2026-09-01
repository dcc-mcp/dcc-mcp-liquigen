"""Import and author a LiquiGen-style chain burst receiver in UE 5.8."""

from __future__ import annotations

from pathlib import Path

from _receiver import create_chain_system, create_material, png_dimensions
from _showcase_common import asset_prefix as validate_prefix
from _showcase_common import chain_config, game_asset_path
from dcc_mcp_core.skill import skill_entry, skill_error, skill_success


@skill_entry
def import_chain_burst(
    source_path: str,
    destination: str,
    asset_prefix: str,
    source_kind: str,
    columns: int = 8,
    rows: int = 8,
    chain_count: int = 5,
    delay_seconds: float = 0.18,
    spacing_cm: float = 260.0,
    **_kwargs,
) -> dict:
    try:
        import unreal

        source = Path(source_path)
        if not source.is_absolute():
            raise ValueError("source_path must be absolute")
        source = source.resolve(strict=True)
        if not source.is_file() or source.suffix.casefold() != ".png":
            raise ValueError("source_path must be an existing PNG file")
        destination = game_asset_path(destination)
        prefix = validate_prefix(asset_prefix)
        if source_kind not in {"liquigen_export", "synthetic_proxy"}:
            raise ValueError("source_kind must be liquigen_export or synthetic_proxy")
        columns, rows = int(columns), int(rows)
        if not 1 <= columns <= 64 or not 1 <= rows <= 64:
            raise ValueError("columns and rows must be between 1 and 64")
        chain = chain_config(chain_count, delay_seconds, spacing_cm)
        width, height = png_dimensions(source)
        if width % columns or height % rows:
            raise ValueError("PNG dimensions are not divisible by the requested grid")

        texture_name = f"T_{prefix}"
        material_name = f"M_{prefix}"
        system_name = f"NS_{prefix}"
        paths = {
            "texture": f"{destination}/{texture_name}",
            "material": f"{destination}/{material_name}",
            "niagara": f"{destination}/{system_name}",
        }
        existing = [
            path for path in paths.values() if unreal.EditorAssetLibrary.does_asset_exist(path)
        ]
        if existing:
            raise RuntimeError("destination assets already exist: " + ", ".join(existing))
        unreal.EditorAssetLibrary.make_directory(destination)

        task = unreal.AssetImportTask()
        task.set_editor_property("filename", str(source))
        task.set_editor_property("destination_path", destination)
        task.set_editor_property("destination_name", texture_name)
        task.set_editor_property("replace_existing", False)
        task.set_editor_property("automated", True)
        task.set_editor_property("save", True)
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        texture = unreal.EditorAssetLibrary.load_asset(paths["texture"])
        if texture is None or not isinstance(texture, unreal.Texture2D):
            raise RuntimeError("texture import failed readback")
        texture.set_editor_property("srgb", True)
        texture.set_editor_property(
            "mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS
        )
        unreal.EditorAssetLibrary.set_metadata_tag(texture, "LiquiGen.SourceKind", source_kind)
        unreal.EditorAssetLibrary.set_metadata_tag(texture, "LiquiGen.SourcePath", str(source))
        unreal.EditorAssetLibrary.set_metadata_tag(texture, "LiquiGen.Grid", f"{columns}x{rows}")
        unreal.EditorAssetLibrary.save_loaded_asset(texture, only_if_is_dirty=False)

        material = create_material(unreal, texture, destination, material_name)
        system = create_chain_system(
            unreal, material, destination, system_name, columns, rows, chain
        )
        for asset in (material, system):
            unreal.EditorAssetLibrary.set_metadata_tag(asset, "LiquiGen.SourceKind", source_kind)
            unreal.EditorAssetLibrary.set_metadata_tag(
                asset, "LiquiGen.ChainCount", str(chain["count"])
            )
            unreal.EditorAssetLibrary.save_loaded_asset(asset, only_if_is_dirty=False)

        verified = {key: unreal.EditorAssetLibrary.load_asset(path) for key, path in paths.items()}
        if any(asset is None for asset in verified.values()):
            raise RuntimeError("authored assets failed readback")
        return skill_success(
            "Imported chain burst receiver into Unreal Engine 5.8",
            source_path=str(source),
            source_kind=source_kind,
            source_dimensions=[width, height],
            frame_dimensions=[width // columns, height // rows],
            grid={"columns": columns, "rows": rows},
            chain=chain,
            texture_path=paths["texture"],
            material_path=paths["material"],
            niagara_path=paths["niagara"],
            verified_classes={key: asset.get_class().get_name() for key, asset in verified.items()},
            prompt="Stage the returned niagara_path with stage_chain_burst.",
        )
    except Exception as exc:
        return skill_error(
            "Failed to import LiquiGen chain burst",
            str(exc),
            possible_solutions=[
                "Use an absolute PNG path with a grid that divides its dimensions.",
                "Choose a new /Game destination or asset_prefix.",
            ],
        )


def main(**kwargs) -> dict:
    return import_chain_burst(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)

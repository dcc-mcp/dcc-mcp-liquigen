"""Cold-start verification for a generated LiquiGen UE flipbook receiver."""

from __future__ import annotations

import json
import os
from pathlib import Path


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _output_path(name: str) -> Path:
    raw = Path(_required(name)).expanduser()
    parent = raw.parent.resolve(strict=True)
    path = parent / raw.name
    if path.exists():
        raise ValueError(f"{name} already exists")
    return path


def _validation_name(unreal, value) -> str:
    result_type = unreal.DataValidationResult
    for name in ("VALID", "INVALID", "NOT_VALIDATED"):
        if value == getattr(result_type, name):
            return name
    return str(value)


def main() -> None:
    import unreal

    result_path = _output_path("LIQUIGEN_UE_VERIFY_RESULT_PATH")
    texture_path = _required("LIQUIGEN_UE_TEXTURE_PATH")
    material_path = _required("LIQUIGEN_UE_MATERIAL_PATH")
    niagara_path = _required("LIQUIGEN_UE_NIAGARA_PATH")

    texture = unreal.EditorAssetLibrary.load_asset(texture_path)
    material = unreal.EditorAssetLibrary.load_asset(material_path)
    niagara = unreal.EditorAssetLibrary.load_asset(niagara_path)
    expected = (
        (texture, unreal.Texture2D, texture_path),
        (material, unreal.Material, material_path),
        (niagara, unreal.NiagaraSystem, niagara_path),
    )
    for asset, asset_type, path in expected:
        if asset is None or not isinstance(asset, asset_type):
            raise RuntimeError(f"asset failed cold-start class readback: {path}")

    expressions = unreal.MaterialEditingLibrary.get_material_expressions(material)
    subuv = [
        expression
        for expression in expressions
        if isinstance(expression, unreal.MaterialExpressionParticleSubUV)
    ]
    if len(subuv) != 1:
        raise RuntimeError(f"expected one ParticleSubUV expression, got {len(subuv)}")
    expression_texture = subuv[0].get_editor_property("texture")
    expression_texture_path = (
        "" if expression_texture is None else expression_texture.get_path_name().split(".", 1)[0]
    )
    if expression_texture_path != texture_path:
        raise RuntimeError("ParticleSubUV texture binding failed cold-start readback")

    asset_subsystem = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
    texture_referencers = [
        str(value)
        for value in asset_subsystem.find_package_referencers_for_asset(texture_path, True)
    ]
    material_referencers = [
        str(value)
        for value in asset_subsystem.find_package_referencers_for_asset(material_path, True)
    ]
    if material_path not in texture_referencers:
        raise RuntimeError("material does not reference the imported texture")
    if niagara_path not in material_referencers:
        raise RuntimeError("Niagara system does not reference the flipbook material")

    validator = unreal.get_editor_subsystem(unreal.EditorValidatorSubsystem)
    validation = {}
    for asset, _asset_type, path in expected:
        validation_result, errors, warnings = validator.is_object_valid(
            asset,
            unreal.DataValidationUsecase.SCRIPT,
        )
        name = _validation_name(unreal, validation_result)
        validation[path] = {
            "result": name,
            "errors": [str(value) for value in errors],
            "warnings": [str(value) for value in warnings],
        }
        if name == "INVALID" or errors:
            raise RuntimeError(f"UE asset validation failed for {path}: {validation[path]}")

    result = {
        "success": True,
        "engine_version": str(unreal.SystemLibrary.get_engine_version()),
        "texture_path": texture_path,
        "material_path": material_path,
        "niagara_path": niagara_path,
        "texture_dimensions": [
            texture.blueprint_get_size_x(),
            texture.blueprint_get_size_y(),
        ],
        "material_expression_classes": [
            expression.get_class().get_name() for expression in expressions
        ],
        "texture_referencers": texture_referencers,
        "material_referencers": material_referencers,
        "validation": validation,
    }
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    unreal.log("LIQUIGEN_UE_VERIFY_RESULT=" + json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

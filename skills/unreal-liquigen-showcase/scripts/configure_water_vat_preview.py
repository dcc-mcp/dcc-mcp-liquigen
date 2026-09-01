"""Configure deterministic playback and visible water look for a finalized VAT instance."""

from __future__ import annotations

import math

from _showcase_common import game_asset_path
from dcc_mcp_core.skill import skill_entry, skill_error, skill_success


@skill_entry
def configure_water_vat_preview(
    material_instance_path: str,
    auto_playback: bool = True,
    support_legacy_parameters: bool = False,
    display_frame: int = 24,
    playback_speed: float = 0.45,
    water_opacity: float = 0.68,
    **_kwargs,
) -> dict:
    try:
        import unreal

        material_instance_path = game_asset_path(material_instance_path)
        if not isinstance(auto_playback, bool):
            raise ValueError("auto_playback must be a boolean")
        if not isinstance(support_legacy_parameters, bool):
            raise ValueError("support_legacy_parameters must be a boolean")
        if isinstance(display_frame, bool) or not isinstance(display_frame, int):
            raise ValueError("display_frame must be an integer")
        if display_frame < 1 or display_frame > 8192:
            raise ValueError("display_frame must be between 1 and 8192")
        for name, value, minimum, maximum in (
            ("playback_speed", playback_speed, 0.01, 10.0),
            ("water_opacity", water_opacity, 0.05, 1.0),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be numeric")
            if not math.isfinite(float(value)) or not minimum <= float(value) <= maximum:
                raise ValueError(f"{name} must be between {minimum} and {maximum}")

        instance = unreal.EditorAssetLibrary.load_asset(material_instance_path)
        if instance is None or instance.get_class().get_name() != "MaterialInstanceConstant":
            raise ValueError("material_instance_path is not a MaterialInstanceConstant")
        library = unreal.MaterialEditingLibrary
        required_scalars = {"Display Frame", "Playback Speed", "Water Opacity"}
        available_scalars = {str(name) for name in library.get_scalar_parameter_names(instance)}
        if not required_scalars.issubset(available_scalars):
            raise RuntimeError("water VAT preview scalar parameters are unavailable")
        available_switches = {
            str(name) for name in library.get_static_switch_parameter_names(instance)
        }
        required_switches = {
            "Auto Playback",
            "Support Legacy Parameters and Instancing",
        }
        if not required_switches.issubset(available_switches):
            raise RuntimeError("water VAT playback mode switches are unavailable")

        scalar_values = {
            "Display Frame": float(display_frame),
            "Playback Speed": float(playback_speed),
            "Water Opacity": float(water_opacity),
        }
        for name, value in scalar_values.items():
            if not library.set_material_instance_scalar_parameter_value(instance, name, value):
                actual = float(library.get_material_instance_scalar_parameter_value(instance, name))
                if not math.isclose(actual, value, rel_tol=1e-6, abs_tol=1e-6):
                    raise RuntimeError("failed to configure water VAT scalar: " + name)
        switch_values = {
            "Auto Playback": auto_playback,
            "Support Legacy Parameters and Instancing": support_legacy_parameters,
        }
        for name, value in switch_values.items():
            changed = library.set_material_instance_static_switch_parameter_value(
                instance, name, value
            )
            switch_value = bool(
                library.get_material_instance_static_switch_parameter_value(instance, name)
            )
            if not changed and switch_value is not value:
                raise RuntimeError("failed to configure water VAT switch: " + name)
        library.update_material_instance(instance)
        if not unreal.EditorAssetLibrary.save_loaded_asset(instance, only_if_is_dirty=False):
            raise RuntimeError("failed to save water VAT preview parameters")

        readback = {
            name: float(library.get_material_instance_scalar_parameter_value(instance, name))
            for name in scalar_values
        }
        for name, value in scalar_values.items():
            if not math.isclose(readback[name], value, rel_tol=1e-6, abs_tol=1e-6):
                raise RuntimeError("water VAT preview readback failed: " + name)
        final_switches = {
            name: bool(library.get_material_instance_static_switch_parameter_value(instance, name))
            for name in switch_values
        }
        for name, value in switch_values.items():
            if final_switches[name] is not value:
                raise RuntimeError("water VAT switch readback failed: " + name)
        return skill_success(
            "Configured LiquiGen water VAT preview",
            material_instance_path=material_instance_path,
            auto_playback=final_switches["Auto Playback"],
            support_legacy_parameters=final_switches[
                "Support Legacy Parameters and Instancing"
            ],
            scalar_values=readback,
        )
    except Exception as exc:
        return skill_error("Failed to configure LiquiGen water VAT preview", str(exc))


def main(**kwargs) -> dict:
    return configure_water_vat_preview(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)

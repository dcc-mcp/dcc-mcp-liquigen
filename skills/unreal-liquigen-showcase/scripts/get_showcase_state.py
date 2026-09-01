"""Verify the current LiquiGen showcase state."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry, skill_error, skill_success


@skill_entry
def get_showcase_state(actor_label: str = "LiquiGen_ChainBurst_Showcase", **_kwargs) -> dict:
    try:
        import unreal

        actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        actor = next(
            (
                item
                for item in actor_subsystem.get_all_level_actors()
                if item.get_actor_label() == actor_label or item.get_name() == actor_label
            ),
            None,
        )
        if actor is None:
            raise ValueError(f"actor not found: {actor_label}")
        component = actor.get_component_by_class(unreal.NiagaraComponent)
        if component is None:
            raise ValueError(f"actor has no NiagaraComponent: {actor_label}")
        system = component.get_asset()
        source_kind = unreal.EditorAssetLibrary.get_metadata_tag(system, "LiquiGen.SourceKind")
        appearance = unreal.EditorAssetLibrary.get_metadata_tag(system, "LiquiGen.Appearance")
        diameter_tag = unreal.EditorAssetLibrary.get_metadata_tag(
            system, "LiquiGen.BlastDiameterCm"
        )
        try:
            blast_diameter_cm = float(str(diameter_tag)) if str(diameter_tag).strip() else None
        except ValueError:
            blast_diameter_cm = None
        scale = actor.get_actor_scale3d()
        return skill_success(
            "LiquiGen showcase state verified",
            actor_label=actor_label,
            actor_path=actor.get_path_name(),
            level_path=actor.get_outermost().get_name(),
            niagara_system_path=system.get_path_name(),
            source_kind=str(source_kind),
            appearance=str(appearance),
            blast_diameter_cm=blast_diameter_cm,
            effect_scale=[scale.x, scale.y, scale.z],
            active=bool(component.is_active()),
            verified=True,
        )
    except Exception as exc:
        return skill_error("Failed to verify LiquiGen showcase", str(exc))


def main(**kwargs) -> dict:
    return get_showcase_state(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)

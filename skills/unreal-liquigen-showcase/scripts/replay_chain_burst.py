"""Restart the staged Niagara chain burst for capture."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry, skill_error, skill_success


@skill_entry
def replay_chain_burst(actor_label: str = "LiquiGen_ChainBurst_Showcase", **_kwargs) -> dict:
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
        component.deactivate()
        component.activate(reset=True)
        return skill_success(
            f"Replayed Niagara chain burst on '{actor_label}'",
            actor_label=actor_label,
            active=bool(component.is_active()),
            prompt="Capture the next three seconds of the viewport.",
        )
    except Exception as exc:
        return skill_error("Failed to replay LiquiGen chain burst", str(exc))


def main(**kwargs) -> dict:
    return replay_chain_burst(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)

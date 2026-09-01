"""Restart the staged Niagara chain burst for capture."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry, skill_error, skill_success


def _actor_matches(actor, label: str) -> bool:
    try:
        actor_label = actor.get_actor_label()
    except Exception:
        actor_label = ""
    return actor_label == label or actor.get_name() == label


@skill_entry
def replay_chain_burst(
    actor_label: str = "LiquiGen_ChainBurst_Showcase",
    hide_default_pawn: bool = False,
    **_kwargs,
) -> dict:
    try:
        import unreal

        if not isinstance(hide_default_pawn, bool):
            raise ValueError("hide_default_pawn must be a boolean")
        game_world = unreal.EditorLevelLibrary.get_game_world()
        runtime_world = game_world is not None
        hidden_pawn_count = 0
        if runtime_world:
            actors = unreal.GameplayStatics.get_all_actors_of_class(game_world, unreal.Actor)
            if hide_default_pawn:
                pawns = unreal.GameplayStatics.get_all_actors_of_class(game_world, unreal.Pawn)
                for pawn in pawns:
                    pawn.set_actor_hidden_in_game(True)
                    pawn.set_actor_enable_collision(False)
                hidden_pawn_count = len(pawns)
        else:
            actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
            actors = actor_subsystem.get_all_level_actors()
        actor = next((item for item in actors if _actor_matches(item, actor_label)), None)
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
            runtime_world=runtime_world,
            hidden_pawn_count=hidden_pawn_count,
            prompt="Capture the next three seconds of the viewport.",
        )
    except Exception as exc:
        return skill_error("Failed to replay LiquiGen chain burst", str(exc))


def main(**kwargs) -> dict:
    return replay_chain_burst(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)

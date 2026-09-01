from dcc_mcp_core.skill import run_main

from dcc_mcp_liquigen.skill_tools import prepare_unreal_water_project


def main(
    source,
    destination,
    output_directory,
    asset_name="LiquiGen_BallDropSplash",
    frame_count=64,
):
    return {
        "success": True,
        "context": prepare_unreal_water_project(
            source,
            destination,
            output_directory,
            asset_name=asset_name,
            frame_count=frame_count,
        ),
    }


if "__mcp_params__" in globals():
    __mcp_result__ = main(**globals()["__mcp_params__"])

if __name__ == "__main__":
    run_main(main)

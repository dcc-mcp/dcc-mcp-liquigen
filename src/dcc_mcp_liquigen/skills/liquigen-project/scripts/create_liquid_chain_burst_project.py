from dcc_mcp_core.skill import run_main

from dcc_mcp_liquigen.skill_tools import create_liquid_chain_burst_project


def main(
    source,
    destination,
    output_directory,
    burst_count=5,
    delay_seconds=0.18,
    spacing_m=2.6,
    export_profile="ue_vat",
):
    return {
        "success": True,
        "context": create_liquid_chain_burst_project(
            source,
            destination,
            output_directory,
            burst_count=burst_count,
            delay_seconds=delay_seconds,
            spacing_m=spacing_m,
            export_profile=export_profile,
        ),
    }


if "__mcp_params__" in globals():
    __mcp_result__ = main(**globals()["__mcp_params__"])

if __name__ == "__main__":
    run_main(main)

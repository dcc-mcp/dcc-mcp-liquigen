from dcc_mcp_core.skill import run_main

from dcc_mcp_liquigen.skill_tools import validate_project


def main(path, require_unreal_export=False):
    return {
        "success": True,
        "context": validate_project(path, require_unreal_export=require_unreal_export),
    }


if "__mcp_params__" in globals():
    __mcp_result__ = main(**globals()["__mcp_params__"])

if __name__ == "__main__":
    run_main(main)

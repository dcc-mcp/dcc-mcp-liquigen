from dcc_mcp_core.skill import run_main

from dcc_mcp_liquigen.skill_tools import stage_project_copy


def main(source, destination):
    return {"success": True, "context": stage_project_copy(source, destination)}


if "__mcp_params__" in globals():
    __mcp_result__ = main(**globals()["__mcp_params__"])

if __name__ == "__main__":
    run_main(main)

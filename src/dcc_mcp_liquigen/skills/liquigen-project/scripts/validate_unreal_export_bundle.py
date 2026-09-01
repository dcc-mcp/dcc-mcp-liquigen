from dcc_mcp_core.skill import run_main

from dcc_mcp_liquigen.skill_tools import validate_unreal_export_bundle


def main(path, columns=None, rows=None):
    return {
        "success": True,
        "context": validate_unreal_export_bundle(path, columns=columns, rows=rows),
    }


if "__mcp_params__" in globals():
    __mcp_result__ = main(**globals()["__mcp_params__"])

if __name__ == "__main__":
    run_main(main)

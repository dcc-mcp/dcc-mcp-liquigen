from dcc_mcp_core.skill import run_main

from dcc_mcp_liquigen.skill_tools import inspect_project_graph


def main(path, node_type="", limit=200):
    return {
        "success": True,
        "context": inspect_project_graph(path, node_type=node_type, limit=limit),
    }


if "__mcp_params__" in globals():
    __mcp_result__ = main(**globals()["__mcp_params__"])

if __name__ == "__main__":
    run_main(main)

from dcc_mcp_core.skill import run_main

from dcc_mcp_liquigen.skill_tools import list_node_schemas


def main(query="", limit=100):
    return {"success": True, "context": list_node_schemas(query=query, limit=limit)}


if "__mcp_params__" in globals():
    __mcp_result__ = main(**globals()["__mcp_params__"])

if __name__ == "__main__":
    run_main(main)

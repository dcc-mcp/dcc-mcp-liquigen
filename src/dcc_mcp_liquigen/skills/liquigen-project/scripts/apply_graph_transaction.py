from dcc_mcp_core.skill import run_main

from dcc_mcp_liquigen.skill_tools import apply_graph_transaction


def main(source, destination, operations, expected_source_sha256=""):
    return {
        "success": True,
        "context": apply_graph_transaction(
            source,
            destination,
            operations,
            expected_source_sha256=expected_source_sha256,
        ),
    }


if "__mcp_params__" in globals():
    __mcp_result__ = main(**globals()["__mcp_params__"])

if __name__ == "__main__":
    run_main(main)

from typing import Mapping, Sequence

from dcc_mcp_liquigen.host_commands import invoke_host_sequence as _invoke_host_sequence


def main(commands: Sequence[Mapping[str, object]]) -> dict[str, object]:
    return _invoke_host_sequence(commands)


if "__mcp_params__" in globals():
    __mcp_result__ = main(**globals()["__mcp_params__"])

from typing import Optional

from dcc_mcp_liquigen.skill_tools import invoke_host_command


def main(
    command: str,
    timeout_ms: int = 5000,
    project_path: Optional[str] = None,
) -> dict[str, object]:
    return invoke_host_command(
        command,
        timeout_ms=timeout_ms,
        project_path=project_path,
    )

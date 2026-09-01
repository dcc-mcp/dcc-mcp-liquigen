from dcc_mcp_liquigen.skill_tools import run_export_workflow


def main(
    project_path: str,
    output_directory: str,
    simulate_seconds: float = 12.0,
    timeout_seconds: float = 600.0,
    stable_seconds: float = 3.0,
    poll_interval_seconds: float = 0.5,
    settle_seconds: float = 2.0,
) -> dict[str, object]:
    return run_export_workflow(
        project_path,
        output_directory,
        simulate_seconds=simulate_seconds,
        timeout_seconds=timeout_seconds,
        stable_seconds=stable_seconds,
        poll_interval_seconds=poll_interval_seconds,
        settle_seconds=settle_seconds,
    )

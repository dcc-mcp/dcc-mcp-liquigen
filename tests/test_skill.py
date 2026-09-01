import json
import runpy
import subprocess
import sys
from pathlib import Path

from dcc_mcp_core import validate_skill


def test_bundled_skill_validates():
    skill = Path(__file__).parents[1] / "src" / "dcc_mcp_liquigen" / "skills" / "liquigen-project"
    report = validate_skill(str(skill))
    errors = [item for item in report.issues if item.severity == "error"]
    assert errors == []


def test_in_process_script_publishes_mcp_result(synthetic_project: Path, monkeypatch):
    skill = Path(__file__).parents[1] / "src" / "dcc_mcp_liquigen" / "skills" / "liquigen-project"
    monkeypatch.setenv("DCC_MCP_LIQUIGEN_ALLOWED_ROOTS", str(synthetic_project.parent))
    module = runpy.run_path(
        str(skill / "scripts" / "inspect_project.py"),
        init_globals={"__mcp_params__": {"path": str(synthetic_project)}},
    )
    result = module["__mcp_result__"]
    assert result["success"] is True
    assert result["context"]["app_id"] == "liquigen"


def test_subprocess_script_emits_full_envelope(synthetic_project: Path, monkeypatch):
    skill = Path(__file__).parents[1] / "src" / "dcc_mcp_liquigen" / "skills" / "liquigen-project"
    monkeypatch.setenv("DCC_MCP_LIQUIGEN_ALLOWED_ROOTS", str(synthetic_project.parent))
    completed = subprocess.run(
        [sys.executable, str(skill / "scripts" / "inspect_project.py")],
        input=json.dumps({"path": str(synthetic_project)}),
        text=True,
        capture_output=True,
        check=True,
    )
    result = json.loads(completed.stdout)
    assert result["success"] is True
    assert result["context"]["app_id"] == "liquigen"


def test_chain_burst_planner_script_exposes_bridge_showcase_contract():
    skill = Path(__file__).parents[1] / "src" / "dcc_mcp_liquigen" / "skills" / "liquigen-project"
    module = runpy.run_path(
        str(skill / "scripts" / "plan_liquid_chain_burst.py"),
        init_globals={
            "__mcp_params__": {
                "output_directory": "F:/exports/liquigen-chain",
                "burst_count": 5,
                "export_profile": "ue_vat",
            }
        },
    )

    result = module["__mcp_result__"]
    assert result["success"] is True
    assert result["context"]["execution_boundary"]["planner_is_read_only"] is True
    assert "typed_graph_operations" in result["context"]["bridge_capabilities"]

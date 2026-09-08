from pathlib import Path

from dcc_mcp_liquigen.runtime import bind_runtime, detect_version


def test_detects_version_from_application_directory():
    executable = Path("C:/Apps/LiquiGen/1.0.5/bin/LiquiGen.exe")
    assert detect_version(executable) == "1.0.5"


def test_explicit_version_wins():
    assert detect_version(Path("LiquiGen.exe"), "1.2.3") == "1.2.3"


def test_environment_version_is_used(monkeypatch):
    monkeypatch.setenv("DCC_MCP_LIQUIGEN_VERSION", "1.2.3")
    assert detect_version(Path("LiquiGen.exe")) == "1.2.3"
    assert detect_version(Path("LiquiGen.exe"), "1.0.5") == "1.0.5"


def test_unrelated_parent_metadata_does_not_set_application_version(tmp_path, monkeypatch):
    monkeypatch.delenv("DCC_MCP_LIQUIGEN_VERSION", raising=False)
    (tmp_path / "package.py").write_text("version = '99.0.0'\n", encoding="utf-8")
    assert detect_version(tmp_path / "bin" / "LiquiGen.exe") == "unknown"


def test_binding_uses_the_exact_window_title():
    class FakeNativeRuntime:
        def process_path(self, pid: int) -> Path:
            assert pid == 2796
            return Path("C:/Apps/LiquiGen.exe")

        def window_title(self, pid: int, window_handle: int) -> str:
            assert (pid, window_handle) == (2796, 349113818)
            return "Open LiquiGen Project"

    binding = bind_runtime(
        2796,
        349113818,
        version="1.0.5",
        inspector=FakeNativeRuntime(),
    )

    assert binding.title == "Open LiquiGen Project"

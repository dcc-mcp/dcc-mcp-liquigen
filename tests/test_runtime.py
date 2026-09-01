from pathlib import Path

from dcc_mcp_liquigen.runtime import bind_runtime, detect_version


def test_detects_thm_package_version_from_path():
    executable = Path("C:/Apps/LiquiGen/1.0.5/bin/LiquiGen.exe")
    assert detect_version(executable) == "1.0.5"


def test_explicit_version_wins():
    assert detect_version(Path("LiquiGen.exe"), "1.2.3") == "1.2.3"


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

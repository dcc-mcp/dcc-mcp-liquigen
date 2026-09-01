from pathlib import Path

from dcc_mcp_liquigen.doctor import diagnose_runtime


def test_doctor_accepts_a_new_version_without_a_host_hash():
    class FakeRuntime:
        def process_path(self, pid: int) -> Path:
            return Path("C:/Apps/LiquiGen.exe")

        def window_title(self, pid: int, window_handle: int) -> str:
            return "LiquiGen"

    report = diagnose_runtime(
        pid=123,
        window_handle=456,
        version="1.8.0",
        inspector=FakeRuntime(),
    )

    assert report["success"] is True
    assert report["compatibility"]["status"] == "compatible_untested"
    assert report["compatibility"]["host_match"]["executable_hash_required"] is False

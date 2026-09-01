"""DCC-MCP composition root for one exact LiquiGen GUI instance."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
from pathlib import Path
from typing import Any, Optional, Sequence

from dcc_mcp_core import DccServerOptions, HostExecutionBridge, MinimalModeConfig
from dcc_mcp_core.server_base import DccServerBase

from .__version__ import __version__
from .runtime import RuntimeBinding, bind_runtime, process_is_alive

logger = logging.getLogger(__name__)
SERVER_NAME = "dcc-mcp-liquigen"
_DCC_NAME = "liquigen"
_BUILTIN_SKILLS_DIR = Path(__file__).resolve().parent / "skills"
_server: Optional["LiquiGenMcpServer"] = None


class LiquiGenMcpServer(DccServerBase):
    """External GUI adapter with typed offline tools and core UI Control fallback."""

    def __init__(
        self,
        *,
        dcc_pid: int,
        dcc_window_handle: int,
        executable: Optional[str] = None,
        dcc_version: Optional[str] = None,
        binding: Optional[RuntimeBinding] = None,
        port: Optional[int] = None,
        extra_skill_paths: Optional[list[str]] = None,
        gateway_port: Optional[int] = None,
        registry_dir: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        self.binding = binding or bind_runtime(
            dcc_pid,
            dcc_window_handle,
            executable=executable,
            version=dcc_version,
        )
        self._extra_skill_paths = list(extra_skill_paths or [])
        os.environ.setdefault("DCC_MCP_PYTHON_EXECUTABLE", sys.executable)
        os.environ["DCC_MCP_LIQUIGEN_PID"] = str(self.binding.pid)
        os.environ["DCC_MCP_LIQUIGEN_WINDOW_HANDLE"] = str(self.binding.window_handle)
        os.environ["DCC_MCP_LIQUIGEN_EXECUTABLE"] = self.binding.executable
        os.environ["DCC_MCP_LIQUIGEN_VERSION"] = self.binding.version
        os.environ["DCC_MCP_UI_CONTROL_PROCESS_ID"] = str(self.binding.pid)
        os.environ["DCC_MCP_UI_CONTROL_WINDOW_HANDLE"] = str(self.binding.window_handle)
        # LiquiGen's SDL/custom-rendered surface exposes only a shallow native root and
        # can stall broad UIA walks while simulation/rendering is active.
        os.environ.setdefault("DCC_MCP_CUA_MAX_DEPTH", "1")
        os.environ.setdefault("DCC_MCP_CUA_MAX_NODES", "32")
        execution_bridge = HostExecutionBridge(dispatcher=None)
        options = DccServerOptions.from_env(
            _DCC_NAME,
            _BUILTIN_SKILLS_DIR,
            port=port,
            server_name=SERVER_NAME,
            server_version=__version__,
            adapter_version=__version__,
            dcc_version=self.binding.version,
            instance_type="gui",
            dcc_pid=self.binding.pid,
            dcc_window_handle=self.binding.window_handle,
            dcc_window_title=self.binding.title,
            execution_bridge=execution_bridge,
            gateway_port=gateway_port,
            registry_dir=registry_dir,
            **kwargs,
        )
        super().__init__(options=options)

    def _version_string(self) -> str:
        return self.binding.version

    @property
    def port(self) -> int:
        if self._handle is not None:
            return int(self._handle.port)
        return int(self._options.port)

    @property
    def mcp_url(self) -> str:
        return "http://127.0.0.1:{}/mcp".format(self.port)

    def register_builtin_actions(
        self,
        extra_skill_paths: Optional[list[str]] = None,
        include_bundled: bool = True,
        minimal_mode: Optional[MinimalModeConfig] = None,
    ) -> None:
        if minimal_mode is None:
            minimal_mode = MinimalModeConfig(
                skills=("liquigen-project",),
                env_var_minimal="DCC_MCP_LIQUIGEN_MINIMAL",
                env_var_default_tools="DCC_MCP_LIQUIGEN_DEFAULT_TOOLS",
            )
        paths = list(self._extra_skill_paths)
        if extra_skill_paths:
            paths.extend(extra_skill_paths)
        super().register_builtin_actions(
            extra_skill_paths=paths,
            include_bundled=include_bundled,
            minimal_mode=minimal_mode,
        )


def start_server(
    *,
    dcc_pid: int,
    dcc_window_handle: int,
    executable: Optional[str] = None,
    dcc_version: Optional[str] = None,
    port: Optional[int] = None,
    extra_skill_paths: Optional[list[str]] = None,
    gateway_port: Optional[int] = None,
    registry_dir: Optional[str] = None,
    **kwargs: Any,
) -> LiquiGenMcpServer:
    global _server
    if _server is None:
        server = LiquiGenMcpServer(
            dcc_pid=dcc_pid,
            dcc_window_handle=dcc_window_handle,
            executable=executable,
            dcc_version=dcc_version,
            port=port,
            extra_skill_paths=extra_skill_paths,
            gateway_port=gateway_port,
            registry_dir=registry_dir,
            **kwargs,
        )
        server.register_builtin_actions()
        server.start()
        _server = server
        logger.info("LiquiGen MCP server started for PID %s", dcc_pid)
    return _server


def stop_server() -> None:
    global _server
    if _server is not None:
        _server.stop()
        _server = None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True, help="Exact LiquiGen process ID")
    parser.add_argument(
        "--window-handle", type=int, required=True, help="Exact native LiquiGen window handle"
    )
    parser.add_argument("--executable", help="Expected LiquiGen executable path")
    parser.add_argument("--version", help="LiquiGen application version")
    parser.add_argument("--port", type=int, default=None, help="MCP port; default is OS assigned")
    parser.add_argument(
        "--allowed-root",
        action="append",
        default=[],
        help="Project/export root allowed by typed tools; repeat as needed",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    if args.allowed_root:
        roots = [str(Path(item).expanduser().resolve(strict=True)) for item in args.allowed_root]
        os.environ["DCC_MCP_LIQUIGEN_ALLOWED_ROOTS"] = os.pathsep.join(roots)
    stopped = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    server = start_server(
        dcc_pid=args.pid,
        dcc_window_handle=args.window_handle,
        executable=args.executable,
        dcc_version=args.version,
        port=args.port,
    )
    try:
        while not stopped.wait(1.0):
            if not process_is_alive(server.binding.pid):
                logger.info("LiquiGen host exited; stopping adapter")
                break
    finally:
        stop_server()


if __name__ == "__main__":
    main()

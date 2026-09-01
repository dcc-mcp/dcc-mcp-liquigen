"""Diagnose one exact LiquiGen process without host-version hash pinning."""

from __future__ import annotations

import argparse
import json
from typing import Optional, Sequence

from .compatibility import BASE_INTERFACES, assess_compatibility
from .runtime import LiquiGenRuntimeError, RuntimeInspector, bind_runtime


def diagnose_runtime(
    *,
    pid: int,
    window_handle: int,
    executable: Optional[str] = None,
    version: Optional[str] = None,
    interfaces: Optional[set[str]] = None,
    inspector: Optional[RuntimeInspector] = None,
) -> dict[str, object]:
    binding = bind_runtime(
        pid,
        window_handle,
        executable=executable,
        version=version,
        inspector=inspector,
    )
    compatibility = assess_compatibility(
        binding,
        interfaces=interfaces if interfaces is not None else BASE_INTERFACES,
    )
    return {
        "success": bool(compatibility["compatible"]),
        "binding": binding.as_dict(),
        "compatibility": compatibility,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--window-handle", type=int, required=True)
    parser.add_argument("--executable")
    parser.add_argument("--version")
    parser.add_argument(
        "--interface",
        action="append",
        dest="interfaces",
        help="Observed named interface; repeat to override built-in base probes",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        report = diagnose_runtime(
            pid=args.pid,
            window_handle=args.window_handle,
            executable=args.executable,
            version=args.version,
            interfaces=set(args.interfaces) if args.interfaces else None,
        )
    except LiquiGenRuntimeError as error:
        print(json.dumps({"success": False, "error": str(error)}, separators=(",", ":")))
        raise SystemExit(2) from error
    print(json.dumps(report, separators=(",", ":")))
    if not report["success"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()


__all__ = ["diagnose_runtime", "main"]

"""evidence-workbench --home generator|validation"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from typing import Sequence

import uvicorn

from evidence_workbench import __version__
from evidence_workbench.app import create_app
from evidence_workbench.settings import HOMES, load_settings


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="evidence-workbench",
        description="Evidence Workbench — local orchestrator for synth-fin + ai-mrg-bench",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument(
        "--home",
        choices=HOMES,
        default="generator",
        help="Initial home (generator=synth-fin, validation=ai-mrg-bench)",
    )
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument(
        "--fake-runners",
        action="store_true",
        help="Use in-process fake runners (default CI / no LFS)",
    )
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    settings = load_settings(host=args.host, port=args.port)
    if args.fake_runners:
        settings = replace(settings, fake_runners=True)

    app = create_app(settings)
    print(
        f"Evidence Workbench · home={args.home} · http://{args.host}:{args.port}/?home={args.home}",
        file=sys.stderr,
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

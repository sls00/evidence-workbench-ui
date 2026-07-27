"""evidence-workbench --home generator|validation"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from typing import Sequence

import uvicorn

from evidence_workbench import __version__
from evidence_workbench.app import create_app
from evidence_workbench.netutil import default_bind_host, public_urls, running_in_wsl
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
    p.add_argument(
        "--host",
        default=None,
        help="Bind address (default: 0.0.0.0 on WSL, else 127.0.0.1)",
    )
    p.add_argument("--port", type=int, default=8765)
    p.add_argument(
        "--fake-runners",
        action="store_true",
        help="Use in-process fake runners (default CI / no LFS)",
    )
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    host = default_bind_host(explicit=args.host)
    settings = load_settings(host=host, port=args.port)
    if args.fake_runners:
        settings = replace(settings, fake_runners=True)

    app = create_app(settings)
    urls = public_urls(host=host, port=args.port, home=args.home)
    print(
        f"Evidence Workbench · home={args.home} · bind={host}:{args.port}",
        file=sys.stderr,
    )
    for u in urls:
        print(f"  → {u}", file=sys.stderr)
    if running_in_wsl() and host in {"0.0.0.0", "::"}:
        print(
            "  WSL: if Windows Edge/curl cannot open 127.0.0.1, see docs/wsl-cursor-browser.md "
            "(mirrored networking). Cursor agent browser MCP may still block loopback — use "
            "system Edge or Playwright-in-WSL.",
            file=sys.stderr,
        )
    uvicorn.run(app, host=host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

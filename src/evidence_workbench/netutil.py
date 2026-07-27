"""WSL / host bind helpers for Windows↔Linux reachability."""

from __future__ import annotations

import os
import socket
from pathlib import Path


def running_in_wsl() -> bool:
    """True when this process is inside WSL (any distro)."""
    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True
    try:
        return "microsoft" in Path("/proc/version").read_text(encoding="utf-8").lower()
    except OSError:
        return False


def default_bind_host(*, explicit: str | None = None) -> str:
    """
    Bind host for uvicorn.

    On WSL, default to 0.0.0.0 so Windows localhost-forward / portproxy / eth0
    can reach the SPA. Non-WSL keeps loopback-only (safer default).
    """
    if explicit is not None:
        return explicit
    return "0.0.0.0" if running_in_wsl() else "127.0.0.1"


def primary_lan_ipv4() -> str | None:
    """Best-effort non-loopback IPv4 (WSL eth0), or None."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
    except OSError:
        pass
    # WSL / restricted nets: parse `ip -4 route get` or eth0 via hostname -I
    try:
        import subprocess

        out = subprocess.check_output(
            ["hostname", "-I"], text=True, timeout=2, stderr=subprocess.DEVNULL
        )
        for tok in out.split():
            if tok and not tok.startswith("127.") and ":" not in tok:
                return tok
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def public_urls(*, host: str, port: int, home: str) -> list[str]:
    """URLs to print for humans / Windows Cursor browser."""
    path = f"/?home={home}"
    urls: list[str] = []
    if host in {"0.0.0.0", "::"}:
        urls.append(f"http://127.0.0.1:{port}{path}")
        lan = primary_lan_ipv4()
        if lan:
            urls.append(f"http://{lan}:{port}{path}")
    else:
        urls.append(f"http://{host}:{port}{path}")
    return urls

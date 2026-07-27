"""Status law: ok | failed | qualified | incomplete."""

from __future__ import annotations

from typing import Literal

RunStatus = Literal["ok", "failed", "qualified", "incomplete", "running", "queued"]
TerminalStatus = Literal["ok", "failed", "qualified", "incomplete"]

TERMINAL: frozenset[str] = frozenset({"ok", "failed", "qualified", "incomplete"})


def map_engine_status(raw: str | None) -> TerminalStatus:
    """Map engine vocabulary onto the locked status law."""
    if raw is None:
        return "failed"
    key = raw.strip().lower()
    if key in {"qualified_pass", "qualified"}:
        return "qualified"
    if key in {"pass", "ok", "success"}:
        return "ok"
    if key in {"fail", "failed", "error"}:
        return "failed"
    if key in {"incomplete", "cancelled", "canceled", "unknown", "unverifiable"}:
        return "incomplete"
    return "failed"


def is_terminal(status: str) -> bool:
    return status in TERMINAL

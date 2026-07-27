"""
Append-only run index (P4).

Contract (ASCII):
  index.jsonl ──append──► one JSON line on TERMINAL state only
  list() skips corrupt lines → footer warning count
  reopen requires primary_report on disk
"""

from __future__ import annotations

import json
import secrets
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evidence_workbench.status import TerminalStatus


def mint_run_id(now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{secrets.token_hex(4)}"


@dataclass(slots=True)
class IndexEntry:
    run_id: str
    namespace: str
    preset_id: str
    created_at: str
    status: TerminalStatus
    config_hash: str | None
    artifact_dir: str
    primary_report: str | None
    extra: dict[str, Any] = field(default_factory=dict)
    home: str | None = None
    finding_title: str | None = None
    finding_subtitle: str | None = None
    verify_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IndexEntry:
        return cls(
            run_id=str(data["run_id"]),
            namespace=str(data["namespace"]),
            preset_id=str(data["preset_id"]),
            created_at=str(data["created_at"]),
            status=data["status"],  # type: ignore[arg-type]
            config_hash=data.get("config_hash"),
            artifact_dir=str(data["artifact_dir"]),
            primary_report=data.get("primary_report"),
            extra=dict(data.get("extra") or {}),
            home=data.get("home"),
            finding_title=data.get("finding_title"),
            finding_subtitle=data.get("finding_subtitle"),
            verify_status=data.get("verify_status"),
        )


@dataclass(slots=True)
class IndexListResult:
    entries: list[IndexEntry]
    corrupt_lines: int
    warnings: list[str]


class RunIndex:
    def __init__(self, runs_root: Path) -> None:
        self.runs_root = runs_root
        self.path = runs_root / "index.jsonl"

    def ensure_root(self) -> None:
        self.runs_root.mkdir(parents=True, exist_ok=True)
        for ns in ("synth-fin", "ai-mrg-bench"):
            (self.runs_root / ns).mkdir(parents=True, exist_ok=True)

    def append(self, entry: IndexEntry) -> None:
        """Append one terminal-state line. artifact_dir must exist."""
        art = Path(entry.artifact_dir)
        if not art.is_dir():
            raise FileNotFoundError(f"artifact_dir missing: {entry.artifact_dir}")
        self.ensure_root()
        line = json.dumps(entry.to_dict(), sort_keys=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def list(
        self,
        *,
        namespace: str | None = None,
        home: str | None = None,
    ) -> IndexListResult:
        if not self.path.is_file():
            return IndexListResult(entries=[], corrupt_lines=0, warnings=[])
        entries: list[IndexEntry] = []
        corrupt = 0
        warnings: list[str] = []
        for i, raw in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
            if not raw.strip():
                continue
            try:
                data = json.loads(raw)
                entry = IndexEntry.from_dict(data)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                corrupt += 1
                warnings.append(f"corrupt index line {i} skipped")
                continue
            if namespace and entry.namespace != namespace:
                continue
            if home and entry.home and entry.home != home:
                continue
            entries.append(entry)
        # newest first
        entries.reverse()
        return IndexListResult(entries=entries, corrupt_lines=corrupt, warnings=warnings)

    def get(self, run_id: str) -> IndexEntry | None:
        result = self.list()
        for entry in result.entries:
            if entry.run_id == run_id:
                return entry
        return None

    def run_dir(self, namespace: str, run_id: str) -> Path:
        return self.runs_root / namespace / run_id

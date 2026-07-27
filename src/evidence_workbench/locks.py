"""
Per-namespace single-flight lock (pid + heartbeat stale reclaim).

State machine (ASCII):
  free ──acquire──► held(pid, heartbeat)
  held ──heartbeat──► held (fresh)
  held ──release──► free
  held ──stale?──► reclaim → free (caller marks orphan run incomplete)
  held ──busy──► 409 Conflict
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

DEFAULT_STALE_SECONDS = 90.0
HEARTBEAT_INTERVAL = 15.0


@dataclass(slots=True)
class LockInfo:
    namespace: str
    run_id: str
    pid: int
    heartbeat_at: float
    acquired_at: float

    def to_dict(self) -> dict:
        return {
            "namespace": self.namespace,
            "run_id": self.run_id,
            "pid": self.pid,
            "heartbeat_at": self.heartbeat_at,
            "acquired_at": self.acquired_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> LockInfo:
        return cls(
            namespace=str(data["namespace"]),
            run_id=str(data["run_id"]),
            pid=int(data["pid"]),
            heartbeat_at=float(data["heartbeat_at"]),
            acquired_at=float(data["acquired_at"]),
        )


class LockBusyError(Exception):
    def __init__(self, info: LockInfo):
        self.info = info
        super().__init__(f"namespace {info.namespace} busy with run {info.run_id}")


class NamespaceLock:
    def __init__(
        self,
        runs_root: Path,
        namespace: str,
        *,
        stale_seconds: float = DEFAULT_STALE_SECONDS,
    ) -> None:
        self.runs_root = runs_root
        self.namespace = namespace
        self.stale_seconds = stale_seconds
        self.lock_dir = runs_root / ".locks"
        self.lock_path = self.lock_dir / f"{namespace}.lock.json"

    def _pid_alive(self, pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def read(self) -> LockInfo | None:
        if not self.lock_path.is_file():
            return None
        try:
            data = json.loads(self.lock_path.read_text(encoding="utf-8"))
            return LockInfo.from_dict(data)
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            return None

    def is_stale(self, info: LockInfo, *, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        if (now - info.heartbeat_at) > self.stale_seconds:
            return True
        if not self._pid_alive(info.pid):
            return True
        return False

def try_acquire(
    lock: NamespaceLock,
    run_id: str,
    *,
    pid: int | None = None,
    now: float | None = None,
) -> tuple[LockInfo, LockInfo | None]:
    """
    Acquire namespace lock.

    Returns (held, reclaimed_or_none).
    Raises LockBusyError when busy with a non-stale lock.
    """
    now = time.time() if now is None else now
    pid = os.getpid() if pid is None else pid
    lock.lock_dir.mkdir(parents=True, exist_ok=True)

    existing = lock.read()
    reclaimed: LockInfo | None = None
    if existing is not None:
        if lock.is_stale(existing, now=now):
            reclaimed = existing
            _atomic_write(lock.lock_path, None)  # clear before rewrite
        else:
            raise LockBusyError(existing)

    info = LockInfo(
        namespace=lock.namespace,
        run_id=run_id,
        pid=pid,
        heartbeat_at=now,
        acquired_at=now,
    )
    _atomic_write(lock.lock_path, info.to_dict())
    return info, reclaimed


def heartbeat(lock: NamespaceLock, run_id: str, *, now: float | None = None) -> None:
    now = time.time() if now is None else now
    existing = lock.read()
    if existing is None or existing.run_id != run_id:
        return
    existing.heartbeat_at = now
    _atomic_write(lock.lock_path, existing.to_dict())


def release(lock: NamespaceLock, run_id: str | None = None) -> None:
    existing = lock.read()
    if existing is None:
        return
    if run_id is not None and existing.run_id != run_id:
        return
    if lock.lock_path.is_file():
        lock.lock_path.unlink(missing_ok=True)


def _atomic_write(path: Path, payload: dict | None) -> None:
    if payload is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)

"""In-memory active runs + terminal index orchestration."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evidence_workbench import locks
from evidence_workbench.locks import LockBusyError, NamespaceLock
from evidence_workbench.presets import default_preset_id
from evidence_workbench.run_index import IndexEntry, RunIndex, mint_run_id
from evidence_workbench.runners import BenchRunner, FakeRunner, RunSnapshot, SynthFinRunner
from evidence_workbench.settings import Settings
from evidence_workbench.status import is_terminal


@dataclass(slots=True)
class ActiveRun:
    run_id: str
    home: str
    namespace: str
    preset_id: str
    artifact_dir: Path
    runner: Any
    created_at: str
    snapshot: RunSnapshot = field(default_factory=lambda: RunSnapshot(status="running"))
    indexed: bool = False


class Orchestrator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.index = RunIndex(settings.runs_root)
        self.index.ensure_root()
        self._active: dict[str, ActiveRun] = {}
        self._lock = threading.RLock()
        self._hb_stop = threading.Event()
        self._hb_thread = threading.Thread(target=self._heartbeat_loop, daemon=True, name="ew-heartbeat")
        self._hb_thread.start()
        self.startup_warnings: list[str] = []
        self.reconcile_startup()

    def reconcile_startup(self) -> None:
        """Reclaim stale locks; note corrupt index lines."""
        warnings: list[str] = []
        for ns in ("synth-fin", "ai-mrg-bench"):
            nlock = NamespaceLock(self.settings.runs_root, ns)
            info = nlock.read()
            if info and nlock.is_stale(info):
                self._mark_incomplete_orphan(ns, info.run_id, reason="stale lock reclaim on startup")
                locks.release(nlock)
                warnings.append(f"Reclaimed stale lock for {ns}/{info.run_id}")
        listed = self.index.list()
        if listed.corrupt_lines:
            warnings.extend(listed.warnings)
        # Orphan dirs without index: leave on disk; mark incomplete if lock pointed there already handled
        self.startup_warnings = warnings

    def _mark_incomplete_orphan(self, namespace: str, run_id: str, *, reason: str) -> None:
        existing = self.index.get(run_id)
        if existing is not None:
            return
        run_dir = self.index.run_dir(namespace, run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        home = "generator" if namespace == "synth-fin" else "validation"
        entry = IndexEntry(
            run_id=run_id,
            namespace=namespace,
            preset_id="unknown",
            created_at=datetime.now(UTC).isoformat(),
            status="incomplete",
            config_hash=None,
            artifact_dir=str(run_dir),
            primary_report=None,
            extra={"reason": reason},
            home=home,
            finding_title="Run incomplete",
            finding_subtitle=reason,
            verify_status="unverifiable" if home == "validation" else None,
        )
        try:
            self.index.append(entry)
        except OSError:
            pass

    def _ns_lock(self, namespace: str) -> NamespaceLock:
        return NamespaceLock(self.settings.runs_root, namespace)

    def _make_runner(self, home: str) -> Any:
        if self.settings.fake_runners:
            return FakeRunner(home=home)
        if home == "generator":
            root = self.settings.synth_fin_root
            if root is None:
                raise RuntimeError("synth_fin_root missing")
            return SynthFinRunner(synth_fin_root=root)
        root = self.settings.ai_mrg_bench_root
        if root is None:
            raise RuntimeError("ai_mrg_bench_root missing")
        return BenchRunner(ai_mrg_bench_root=root)

    def start_run(self, home: str, preset_id: str | None = None) -> ActiveRun:
        preset_id = preset_id or default_preset_id(home)  # type: ignore[arg-type]
        namespace = self.settings.namespace_for(home)
        run_id = mint_run_id()
        run_dir = self.index.run_dir(namespace, run_id)
        run_dir.mkdir(parents=True, exist_ok=True)

        nlock = self._ns_lock(namespace)
        try:
            _held, reclaimed = locks.try_acquire(nlock, run_id)
        except LockBusyError as exc:
            raise BusyError(exc.info.run_id, namespace) from exc

        if reclaimed is not None:
            self._mark_incomplete_orphan(
                namespace,
                reclaimed.run_id,
                reason="stale lock reclaim before new run",
            )

        runner = self._make_runner(home)
        active = ActiveRun(
            run_id=run_id,
            home=home,
            namespace=namespace,
            preset_id=preset_id,
            artifact_dir=run_dir,
            runner=runner,
            created_at=datetime.now(UTC).isoformat(),
            snapshot=RunSnapshot(status="running"),
        )
        with self._lock:
            self._active[run_id] = active
        runner.start(preset_id, run_dir)
        return active

    def poll(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            active = self._active.get(run_id)
        if active is not None:
            snap = active.runner.poll()
            active.snapshot = snap
            if is_terminal(snap.status) and not active.indexed:
                self._finalize(active, snap)
            return self._snapshot_payload(active, snap)

        entry = self.index.get(run_id)
        if entry is None:
            raise KeyError(run_id)
        return self._entry_payload(entry)

    def cancel(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            active = self._active.get(run_id)
        if active is None:
            raise KeyError(run_id)
        active.runner.cancel()
        snap = active.runner.poll()
        if snap.status != "incomplete":
            snap = RunSnapshot(
                status="incomplete",
                finding_title="Run incomplete",
                finding_subtitle="Cancelled",
                verify_status="unverifiable" if active.home == "validation" else None,
                primary_report=snap.primary_report,
                extra=snap.extra,
            )
        active.snapshot = snap
        if not active.indexed:
            self._finalize(active, snap)
        return self._snapshot_payload(active, snap)

    def reverify(self, run_id: str) -> dict[str, Any]:
        entry = self.index.get(run_id)
        if entry is None:
            # maybe still active
            with self._lock:
                active = self._active.get(run_id)
            if active is None:
                raise KeyError(run_id)
            if active.home != "validation":
                raise ValueError("reverify only on validation home")
            runner = active.runner
            if isinstance(runner, (BenchRunner, FakeRunner)):
                if isinstance(runner, BenchRunner):
                    snap = runner.reverify(active.artifact_dir)
                else:
                    snap = runner.poll()
                    snap.verify_status = snap.verify_status or "PASS"
                active.snapshot = snap
                return self._snapshot_payload(active, snap)
            raise ValueError("runner cannot reverify")

        if entry.home != "validation" and entry.namespace != "ai-mrg-bench":
            raise ValueError("reverify only on validation home")
        if self.settings.fake_runners:
            verify = entry.verify_status or "PASS"
            return {
                "status": entry.status,
                "run_id": entry.run_id,
                "verify_status": verify,
                "verify_breaks": [],
                "primary_report": entry.primary_report,
                "artifacts_missing": not _report_exists(entry),
            }
        runner = BenchRunner(ai_mrg_bench_root=self.settings.ai_mrg_bench_root)  # type: ignore[arg-type]
        snap = runner.reverify(Path(entry.artifact_dir))
        return {
            "status": snap.status,
            "run_id": run_id,
            "verify_status": snap.verify_status,
            "verify_breaks": snap.verify_breaks,
            "finding_title": snap.finding_title,
            "finding_subtitle": snap.finding_subtitle,
            "primary_report": snap.primary_report,
            "error": snap.error,
            "artifacts_missing": snap.primary_report is None or not Path(snap.primary_report).is_file(),
        }

    def list_runs(self, home: str) -> dict[str, Any]:
        namespace = self.settings.namespace_for(home)
        result = self.index.list(namespace=namespace)
        rows = []
        for entry in result.entries:
            rows.append({
                **entry.to_dict(),
                "artifacts_missing": not _report_exists(entry),
            })
        # include active non-terminal for this home
        with self._lock:
            for active in self._active.values():
                if active.home == home and not is_terminal(active.snapshot.status):
                    rows.insert(0, {
                        "run_id": active.run_id,
                        "namespace": active.namespace,
                        "preset_id": active.preset_id,
                        "created_at": active.created_at,
                        "status": active.snapshot.status,
                        "config_hash": active.snapshot.config_hash,
                        "artifact_dir": str(active.artifact_dir),
                        "primary_report": active.snapshot.primary_report,
                        "home": active.home,
                        "finding_title": active.snapshot.finding_title,
                        "artifacts_missing": False,
                    })
        return {
            "runs": rows,
            "corrupt_lines": result.corrupt_lines,
            "warnings": result.warnings + self.startup_warnings,
        }

    def report_path(self, run_id: str) -> Path:
        with self._lock:
            active = self._active.get(run_id)
        if active is not None and active.snapshot.primary_report:
            path = Path(active.snapshot.primary_report).resolve()
            self._assert_under_run(active.artifact_dir, path)
            return path
        entry = self.index.get(run_id)
        if entry is None or not entry.primary_report:
            raise FileNotFoundError(run_id)
        path = Path(entry.primary_report).resolve()
        self._assert_under_run(Path(entry.artifact_dir), path)
        return path

    def _run_context(self, run_id: str) -> tuple[str, str, str, Path]:
        """Return (home, status, run_id, run_dir) for artifact APIs."""
        with self._lock:
            active = self._active.get(run_id)
        if active is not None:
            snap = active.runner.poll()
            active.snapshot = snap
            if is_terminal(snap.status) and not active.indexed:
                self._finalize(active, snap)
            return active.home, snap.status, active.run_id, active.artifact_dir
        entry = self.index.get(run_id)
        if entry is None:
            raise KeyError(run_id)
        home = entry.home or ("generator" if entry.namespace == "synth-fin" else "validation")
        return home, entry.status, entry.run_id, Path(entry.artifact_dir)

    def timeline(self, run_id: str) -> dict[str, Any]:
        from evidence_workbench.artifacts import build_timeline

        home, status, rid, run_dir = self._run_context(run_id)
        self._assert_under_run(run_dir, run_dir.resolve())
        return build_timeline(run_id=rid, home=home, status=status, run_dir=run_dir)

    def inspect(self, run_id: str) -> dict[str, Any]:
        from evidence_workbench.artifacts import build_inspect

        home, status, rid, run_dir = self._run_context(run_id)
        self._assert_under_run(run_dir, run_dir.resolve())
        return build_inspect(run_id=rid, home=home, status=status, run_dir=run_dir)

    def compare(self, home: str, left_id: str, right_id: str) -> dict[str, Any]:
        from evidence_workbench.artifacts import build_compare

        if left_id == right_id:
            raise ValueError("same_run")
        left_home, left_status, _, left_dir = self._run_context(left_id)
        right_home, right_status, _, right_dir = self._run_context(right_id)
        if left_home != home or right_home != home:
            raise ValueError("cross_home")
        self._assert_under_run(left_dir, left_dir.resolve())
        self._assert_under_run(right_dir, right_dir.resolve())
        left_meta = self._compare_meta(left_id, left_home, left_status)
        right_meta = self._compare_meta(right_id, right_home, right_status)
        return build_compare(
            home=home,
            left_meta=left_meta,
            right_meta=right_meta,
            left_dir=left_dir,
            right_dir=right_dir,
        )

    def _compare_meta(self, run_id: str, home: str, status: str) -> dict[str, Any]:
        with self._lock:
            active = self._active.get(run_id)
        if active is not None:
            snap = active.snapshot
            return {
                "run_id": run_id,
                "preset_id": active.preset_id,
                "config_hash": snap.config_hash,
                "status": status,
                "verify_status": snap.verify_status,
            }
        entry = self.index.get(run_id)
        if entry is None:
            raise KeyError(run_id)
        return {
            "run_id": run_id,
            "preset_id": entry.preset_id,
            "config_hash": entry.config_hash,
            "status": status,
            "verify_status": entry.verify_status,
        }

    def _assert_under_run(self, run_dir: Path, path: Path) -> None:
        run_dir = run_dir.resolve()
        try:
            path.relative_to(run_dir)
        except ValueError as exc:
            # also allow under runs_root namespace
            try:
                path.relative_to(self.settings.runs_root.resolve())
            except ValueError:
                raise PermissionError("report path escapes runs root") from exc
        # reject .. traversal already handled by resolve + relative_to

    def _finalize(self, active: ActiveRun, snap: RunSnapshot) -> None:
        entry = IndexEntry(
            run_id=active.run_id,
            namespace=active.namespace,
            preset_id=active.preset_id,
            created_at=active.created_at,
            status=snap.terminal_status() or "failed",  # type: ignore[arg-type]
            config_hash=snap.config_hash,
            artifact_dir=str(active.artifact_dir),
            primary_report=snap.primary_report,
            extra=dict(snap.extra or {}),
            home=active.home,
            finding_title=snap.finding_title,
            finding_subtitle=snap.finding_subtitle,
            verify_status=snap.verify_status,
        )
        try:
            self.index.append(entry)
            active.indexed = True
        finally:
            locks.release(self._ns_lock(active.namespace), active.run_id)
            with self._lock:
                # keep briefly for poll; leave in _active until next list — ok to keep
                pass

    def _heartbeat_loop(self) -> None:
        while not self._hb_stop.wait(locks.HEARTBEAT_INTERVAL):
            with self._lock:
                actives = list(self._active.values())
            for active in actives:
                if is_terminal(active.snapshot.status):
                    continue
                try:
                    locks.heartbeat(self._ns_lock(active.namespace), active.run_id)
                except OSError:
                    pass

    def shutdown(self) -> None:
        self._hb_stop.set()

    def _snapshot_payload(self, active: ActiveRun, snap: RunSnapshot) -> dict[str, Any]:
        return {
            "status": snap.status,
            "run_id": active.run_id,
            "home": active.home,
            "namespace": active.namespace,
            "preset_id": active.preset_id,
            "created_at": active.created_at,
            "finding_title": snap.finding_title,
            "finding_subtitle": snap.finding_subtitle,
            "config_hash": snap.config_hash,
            "primary_report": snap.primary_report,
            "pillars": snap.pillars,
            "verify_status": snap.verify_status,
            "verify_breaks": snap.verify_breaks,
            "extra": snap.extra,
            "error": snap.error,
            "artifacts_missing": bool(
                is_terminal(snap.status)
                and (not snap.primary_report or not Path(snap.primary_report).is_file())
            ),
            "report_url": f"/api/runs/{active.run_id}/report" if snap.primary_report else None,
        }

    def _entry_payload(self, entry: IndexEntry) -> dict[str, Any]:
        missing = not _report_exists(entry)
        return {
            **entry.to_dict(),
            "pillars": [],
            "verify_breaks": [],
            "artifacts_missing": missing,
            "report_url": None if missing else f"/api/runs/{entry.run_id}/report",
            "error": {"code": "artifacts_missing", "message": "artifacts missing", "hint": "Primary report not on disk"}
            if missing
            else None,
        }


class BusyError(Exception):
    def __init__(self, run_id: str, namespace: str) -> None:
        self.run_id = run_id
        self.namespace = namespace
        super().__init__(f"{namespace} busy with {run_id}")


def _report_exists(entry: IndexEntry) -> bool:
    if not entry.primary_report:
        return False
    return Path(entry.primary_report).is_file()

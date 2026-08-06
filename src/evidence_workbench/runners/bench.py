"""ai-mrg-bench ValidationRun child process + verify-chain."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from evidence_workbench.presets import get_validation_preset
from evidence_workbench.runners.base import (
    RunSnapshot,
    spawn_process_group,
    terminate_process_group,
)


_CHILD_MODULE = r"""
from __future__ import annotations
import json
import sys
from pathlib import Path

def main() -> int:
    config_path = Path(sys.argv[1])
    run_dir = Path(sys.argv[2])
    run_id = sys.argv[3]
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = run_dir / "workbench.db"

    # Ensure cwd is bench root so relative configs/models resolve
    from workbench.sdk import ValidationRun
    from workbench.audit import verify_audit_chain

    run = ValidationRun.from_config(config_path)
    run.config.run_id = run_id
    run.config.outputs.artifact_dir_template = str(run_dir)
    run.config.audit.db_path = db_path
    try:
        result = run.run()
        verification = verify_audit_chain(db_path)
        payload = {
            "ok": True,
            "run_id": result.run_id,
            "artifact_dir": str(result.artifact_dir),
            "report_path": str(result.report_path),
            "verify_status": verification.status,
            "verify_breaks": [
                {"index": getattr(b, "index", i), "reason": str(b)}
                for i, b in enumerate(getattr(verification, "breaks", []) or [])
            ],
            "event_counts": dict(getattr(verification, "event_type_counts", {}) or {}),
        }
    except Exception as exc:
        payload = {
            "ok": False,
            "error": str(exc),
            "verify_status": "unknown",
            "verify_breaks": [],
        }
        (run_dir / "runner_result.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return 1
    (run_dir / "runner_result.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
"""


class BenchRunner:
    def __init__(self, *, ai_mrg_bench_root: Path) -> None:
        self.root = ai_mrg_bench_root
        self._thread: threading.Thread | None = None
        self._snapshot = RunSnapshot(status="queued")
        self._lock = threading.Lock()
        self._proc: Any = None
        self._cancel = threading.Event()
        self._run_dir: Path | None = None

    def start(self, preset_id: str, run_dir: Path) -> None:
        preset = get_validation_preset(preset_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        self._run_dir = run_dir
        with self._lock:
            self._snapshot = RunSnapshot(status="running")
            self._cancel.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(preset, run_dir),
            daemon=True,
            name=f"bench-{preset_id}",
        )
        self._thread.start()

    def poll(self) -> RunSnapshot:
        with self._lock:
            return self._snapshot

    def cancel(self) -> None:
        self._cancel.set()
        if self._proc is not None:
            terminate_process_group(self._proc)
        with self._lock:
            if self._snapshot.terminal_status() is None:
                self._snapshot = RunSnapshot(
                    status="incomplete",
                    finding_title="Run incomplete",
                    finding_subtitle="Cancelled mid-audit; verify unknown/unverifiable",
                    verify_status="unverifiable",
                )

    def reverify(self, run_dir: Path) -> RunSnapshot:
        """Re-run verify_audit_chain against nested DB (same verifier)."""
        db_path = run_dir / "workbench.db"
        if not db_path.is_file() or db_path.stat().st_size == 0:
            return RunSnapshot(
                status="incomplete",
                verify_status="unverifiable",
                finding_title="Verify unavailable",
                finding_subtitle="Audit DB missing or empty — never fake PASS from torn DB",
                primary_report=_find_report(run_dir),
            )
        # Prefer subprocess verify in bench env (sibling venv); import only if present.
        import importlib.util
        import json as _json

        if importlib.util.find_spec("workbench") is not None:
            try:
                from workbench.audit import verify_audit_chain

                verification = verify_audit_chain(db_path)
                breaks = [
                    {"index": getattr(b, "index", i), "reason": str(b)}
                    for i, b in enumerate(getattr(verification, "breaks", []) or [])
                ]
                return RunSnapshot(
                    status="ok" if verification.status == "PASS" else "failed",
                    verify_status=verification.status,
                    verify_breaks=breaks,
                    finding_title=f"Verify {verification.status}",
                    finding_subtitle=f"{verification.total_events} events",
                    primary_report=_find_report(run_dir),
                    extra={"workbench_db": str(db_path)},
                )
            except Exception as exc:  # noqa: BLE001
                return RunSnapshot(
                    status="incomplete",
                    verify_status="unknown",
                    finding_title="Verify unknown",
                    finding_subtitle=str(exc),
                    primary_report=_find_report(run_dir),
                    error={"code": "verify_exception", "message": str(exc), "hint": "DB may be torn"},
                )

        result_path = run_dir / "reverify_result.json"
        script = run_dir / "_reverify_child.py"
        script.write_text(
            "from pathlib import Path\n"
            "import json, sys\n"
            "from workbench.audit import verify_audit_chain\n"
            "db = Path(sys.argv[1]); out = Path(sys.argv[2])\n"
            "try:\n"
            "  v = verify_audit_chain(db)\n"
            "  out.write_text(json.dumps({'ok': True, 'status': v.status, "
            "'events': v.total_events, 'breaks': [str(b) for b in v.breaks]}))\n"
            "except Exception as e:\n"
            "  out.write_text(json.dumps({'ok': False, 'error': str(e), 'status': 'unknown'}))\n"
            "  raise SystemExit(1)\n",
            encoding="utf-8",
        )
        proc = spawn_process_group(
            [
                "uv",
                "run",
                "--directory",
                str(self.root),
                "python",
                str(script),
                str(db_path),
                str(result_path),
            ],
            cwd=self.root,
        )
        _stdout, stderr = proc.communicate()
        if result_path.is_file():
            payload = _json.loads(result_path.read_text(encoding="utf-8"))
            if payload.get("ok"):
                breaks = [{"reason": b} for b in payload.get("breaks") or []]
                return RunSnapshot(
                    status="ok" if payload.get("status") == "PASS" else "failed",
                    verify_status=payload.get("status"),
                    verify_breaks=breaks,
                    finding_title=f"Verify {payload.get('status')}",
                    finding_subtitle=f"{payload.get('events', 0)} events",
                    primary_report=_find_report(run_dir),
                    extra={"workbench_db": str(db_path)},
                )
            return RunSnapshot(
                status="incomplete",
                verify_status=payload.get("status") or "unknown",
                finding_title="Verify unknown",
                finding_subtitle=str(payload.get("error") or stderr or "")[:300],
                primary_report=_find_report(run_dir),
                error={
                    "code": "verify_exception",
                    "message": str(payload.get("error")),
                    "hint": "DB may be torn",
                },
            )
        return RunSnapshot(
            status="incomplete",
            verify_status="unknown",
            finding_title="Verify unknown",
            finding_subtitle=(stderr or "reverify failed")[:300],
            primary_report=_find_report(run_dir),
            error={
                "code": "verify_exception",
                "message": stderr or "failed",
                "hint": "DB may be torn",
            },
        )

    def _set(self, snap: RunSnapshot) -> None:
        with self._lock:
            self._snapshot = snap

    def _run(self, preset: Any, run_dir: Path) -> None:
        config_path = (self.root / preset.config_relpath).resolve()
        child_path = run_dir / "_bench_child.py"
        child_path.write_text(_CHILD_MODULE, encoding="utf-8")
        # Use orchestrator run_id directory name as ValidationRun run_id
        run_id = run_dir.name
        # Run child inside ai-mrg-bench uv env (pandas conflict with synth-fin).
        argv = [
            "uv",
            "run",
            "--directory",
            str(self.root),
            "python",
            str(child_path),
            str(config_path),
            str(run_dir),
            run_id,
        ]
        try:
            proc = spawn_process_group(argv, cwd=self.root)
            self._proc = proc
            stdout, stderr = proc.communicate()
            self._proc = None
            if self._cancel.is_set():
                self._set(
                    RunSnapshot(
                        status="incomplete",
                        finding_title="Run incomplete",
                        finding_subtitle="Cancelled mid-audit; verify unknown/unverifiable",
                        verify_status="unverifiable",
                        primary_report=_find_report(run_dir),
                    )
                )
                return
            result_path = run_dir / "runner_result.json"
            if result_path.is_file():
                payload = json.loads(result_path.read_text(encoding="utf-8"))
            else:
                payload = {
                    "ok": False,
                    "error": (stderr or stdout or "no runner_result.json")[:500],
                    "verify_status": "unknown",
                }
            if not payload.get("ok"):
                self._set(
                    RunSnapshot(
                        status="failed",
                        finding_title="Validation failed",
                        finding_subtitle=str(payload.get("error") or "engine exception"),
                        verify_status=payload.get("verify_status") or "unknown",
                        primary_report=_find_report(run_dir),
                        error={
                            "code": "bench_failed",
                            "message": str(payload.get("error") or "failed"),
                            "hint": "Inspect run directory and workbench logs",
                        },
                        extra={"workbench_db": str(run_dir / "workbench.db")},
                    )
                )
                return
            report = payload.get("report_path") or _find_report(run_dir)
            self._set(
                RunSnapshot(
                    status="ok",
                    finding_title="Validation complete",
                    finding_subtitle=f"preset={preset.id}",
                    primary_report=report,
                    verify_status=payload.get("verify_status"),
                    verify_breaks=list(payload.get("verify_breaks") or []),
                    config_hash=None,
                    extra={
                        "workbench_db": str(run_dir / "workbench.db"),
                        "runner_result": str(result_path),
                    },
                )
            )
        except Exception as exc:  # noqa: BLE001
            self._set(
                RunSnapshot(
                    status="failed",
                    finding_title="Validation runner error",
                    finding_subtitle=str(exc),
                    verify_status="unknown",
                    error={"code": "runner_exception", "message": str(exc), "hint": "Check AI_MRG_BENCH_ROOT"},
                )
            )


def _find_report(run_dir: Path) -> str | None:
    for name in (
        "validation_report.md",
        "report.md",
        "report.html",
    ):
        p = run_dir / name
        if p.is_file():
            return str(p)
    md = list(run_dir.glob("*validation_report*.md"))
    if md:
        return str(md[0])
    return None

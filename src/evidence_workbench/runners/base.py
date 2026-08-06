"""
Runner protocol + child-process helpers.

Lifecycle (ASCII):
  start(preset, run_dir) ──spawn pg──► running
  poll() ──read snapshot──► running | terminal
  cancel() ──SIGTERM pg──wait──SIGKILL──► incomplete
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from evidence_workbench.status import TerminalStatus, map_engine_status


@dataclass(slots=True)
class RunSnapshot:
    status: str  # running | ok | failed | qualified | incomplete
    finding_title: str | None = None
    finding_subtitle: str | None = None
    config_hash: str | None = None
    primary_report: str | None = None
    pillars: list[dict[str, Any]] = field(default_factory=list)
    verify_status: str | None = None  # PASS | FAIL | unknown | unverifiable
    verify_breaks: list[dict[str, Any]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)
    error: dict[str, str] | None = None

    def terminal_status(self) -> TerminalStatus | None:
        if self.status in {"ok", "failed", "qualified", "incomplete"}:
            return self.status  # type: ignore[return-value]
        return None


class Runner(Protocol):
    def start(self, preset_id: str, run_dir: Path) -> None: ...
    def poll(self) -> RunSnapshot: ...
    def cancel(self) -> None: ...


def map_synth_overall(overall_state: str | None) -> TerminalStatus:
    return map_engine_status(overall_state)


def terminate_process_group(
    proc: subprocess.Popen[Any],
    *,
    grace_seconds: float = 2.0,
) -> None:
    """SIGTERM → wait → SIGKILL the process group."""
    if proc.poll() is not None:
        return
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        return
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.time() + grace_seconds
    while time.time() < deadline:
        if proc.poll() is not None:
            return
        time.sleep(0.05)
    if proc.poll() is None:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass


def spawn_process_group(
    argv: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.Popen[Any]:
    merged = dict(os.environ)
    if env:
        merged.update(env)
    return subprocess.Popen(
        argv,
        cwd=str(cwd) if cwd else None,
        env=merged,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )


def _env_fake_delay(default: float = 0.15) -> float:
    raw = os.environ.get("EVIDENCE_FAKE_RUNNER_DELAY", "").strip()
    if not raw:
        return default
    try:
        return max(0.0, float(raw))
    except ValueError:
        return default


def _env_fake_hang() -> bool:
    return os.environ.get("EVIDENCE_FAKE_RUNNER_HANG", "").lower() in {"1", "true", "yes"}


class FakeRunner:
    """Deterministic in-process runner for default CI (no LFS / engines)."""

    def __init__(
        self,
        *,
        home: str,
        delay_seconds: float | None = None,
        outcome: str = "ok",
        hang: bool | None = None,
    ) -> None:
        self.home = home
        self.delay_seconds = _env_fake_delay() if delay_seconds is None else delay_seconds
        self.outcome = outcome
        self.hang = _env_fake_hang() if hang is None else hang
        self._started_at: float | None = None
        self._run_dir: Path | None = None
        self._preset_id: str | None = None
        self._cancelled = False
        self._terminal: RunSnapshot | None = None
        self._lock = threading.Lock()

    def start(self, preset_id: str, run_dir: Path) -> None:
        self._preset_id = preset_id
        self._run_dir = run_dir
        run_dir.mkdir(parents=True, exist_ok=True)
        self._started_at = time.time()
        self._cancelled = False
        self._terminal = None

    def poll(self) -> RunSnapshot:
        with self._lock:
            if self._terminal is not None:
                return self._terminal
            if self._cancelled:
                snap = self._make_incomplete()
                self._terminal = snap
                return snap
            if self._started_at is None:
                return RunSnapshot(status="failed", error={
                    "code": "not_started",
                    "message": "Runner not started",
                    "hint": "Call start() before poll()",
                })
            if self.hang or (time.time() - self._started_at) < self.delay_seconds:
                return RunSnapshot(status="running")
            snap = self._make_terminal()
            self._terminal = snap
            return snap

    def cancel(self) -> None:
        with self._lock:
            self._cancelled = True
            if self._terminal is None or self._terminal.status == "running":
                self._terminal = self._make_incomplete()

    def _make_incomplete(self) -> RunSnapshot:
        assert self._run_dir is not None
        verify = "unverifiable" if self.home == "validation" else None
        return RunSnapshot(
            status="incomplete",
            finding_title="Run incomplete",
            finding_subtitle="Cancelled or reclaimed before terminal artifacts settled",
            primary_report=None,
            verify_status=verify,
            extra={"preset_id": self._preset_id},
        )

    def _make_terminal(self) -> RunSnapshot:
        assert self._run_dir is not None and self._preset_id is not None
        run_dir = self._run_dir
        if self.home == "generator":
            return self._synth_artifacts(run_dir)
        return self._bench_artifacts(run_dir)

    def _synth_artifacts(self, run_dir: Path) -> RunSnapshot:
        status = self.outcome if self.outcome in {"ok", "failed", "qualified"} else "ok"
        bias_by_preset = {
            "bias_demo_1k": {"subgroup_gap_pp": 7.6, "bottom_quartile_pct": 3.2, "top_quartile_pct": 10.8},
            "base_1k": {"subgroup_gap_pp": 0.1, "bottom_quartile_pct": 2.5, "top_quartile_pct": 2.6},
            "rate_shock_1k": {"subgroup_gap_pp": 4.2, "bottom_quartile_pct": 2.8, "top_quartile_pct": 7.1},
        }
        hash_by_preset = {
            "bias_demo_1k": "sf_fake_biasdemo",
            "base_1k": "sf_fake_base1k",
            "rate_shock_1k": "sf_fake_rateshock",
        }
        bias = bias_by_preset.get(self._preset_id or "", bias_by_preset["bias_demo_1k"])
        config_hash = hash_by_preset.get(self._preset_id or "", "sf_fake_deadbeef")
        validation = {
            "overall_state": {
                "ok": "pass",
                "qualified": "qualified_pass",
                "failed": "fail",
            }[status],
            "pillars": {
                "privacy": {"state": "pass"},
                "utility": {"state": "qualified_pass" if status == "qualified" else "pass"},
                "fidelity": {"state": "fail" if status == "failed" else "pass"},
            },
            "bias": bias,
        }
        (run_dir / "validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
        panel = run_dir / "panel"
        panel.mkdir(parents=True, exist_ok=True)
        (panel / "validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
        manifest = {
            "config_hash": config_hash,
            "bias_profile": self._preset_id,
            "stages": [
                {"stage": "cli.parse", "preset": self._preset_id},
                {"stage": "seed.load", "n_seed": 1000},
                {"stage": "copula.sample", "n": 1000},
                {"stage": "bias.apply", "profile": self._preset_id},
                {"stage": "io.write"},
            ],
        }
        (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        (panel / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        report = run_dir / "report.html"
        report.write_text(
            "<!doctype html><html><body><h1>Fake synth-fin report</h1>"
            f"<p>preset={self._preset_id}</p></body></html>",
            encoding="utf-8",
        )
        pillars = [
            {"name": "Privacy", "state": map_engine_status("pass")},
            {
                "name": "Utility",
                "state": map_engine_status(
                    "qualified_pass" if status == "qualified" else "pass"
                ),
            },
            {
                "name": "Fidelity",
                "state": map_engine_status("fail" if status == "failed" else "pass"),
            },
        ]
        return RunSnapshot(
            status=status,
            finding_title=f"Subgroup gap +{bias['subgroup_gap_pp']}pp" if status != "failed" else "Validation failed",
            finding_subtitle=(
                f"Bottom quartile {bias['bottom_quartile_pct']}% → top quartile {bias['top_quartile_pct']}% "
                "(manifest ground truth)"
            ),
            config_hash=config_hash,
            primary_report=str(report),
            pillars=pillars,
            extra={
                "validation_json": str(run_dir / "validation.json"),
                "manifest_json": str(run_dir / "manifest.json"),
            },
        )

    def _bench_artifacts(self, run_dir: Path) -> RunSnapshot:
        status = self.outcome if self.outcome in {"ok", "failed", "qualified"} else "ok"
        battery_by_preset = {
            "gc_full": {"protected_attribute": "sex", "reference_group": "male", "run_id": "fake-gc-full"},
            "gc_ca_overlay": {"protected_attribute": "sex", "reference_group": "female", "run_id": "fake-gc-ca"},
            "cre_p5": {"protected_attribute": "region", "reference_group": "urban", "run_id": "fake-cre-p5"},
        }
        hash_by_preset = {
            "gc_full": "wb_fake_gc_full",
            "gc_ca_overlay": "wb_fake_gc_ca",
            "cre_p5": "wb_fake_cre_p5",
        }
        battery = battery_by_preset.get(self._preset_id or "", battery_by_preset["gc_full"])
        config_hash = hash_by_preset.get(self._preset_id or "", "wb_fake_cafebabe")
        report = run_dir / "validation_report.md"
        report.write_text(
            "# Fake OCC report\n\n## §I Scope\n\nDisclaimer.\n\n## §II Limitations\n\nLimits.\n",
            encoding="utf-8",
        )
        verify = "PASS" if status == "ok" else ("FAIL" if status == "failed" else "PASS")
        (run_dir / "bias_battery_summary.json").write_text(
            json.dumps(
                {
                    "status": verify,
                    "protected_attribute": battery["protected_attribute"],
                    "reference_group": battery["reference_group"],
                    "jurisdiction_frame": "demo",
                    "run_id": battery["run_id"],
                    "aequitas_pin": "fake",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (run_dir / "drift_report.json").write_text(
            json.dumps(
                {
                    "overall_alert_level": "none",
                    "materiality_tier": "low",
                    "recommended_action": "monitor",
                    "run_id": "fake-gc",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (run_dir / "translation_methodology_v1.json").write_text(
            json.dumps({"version": "v1", "methodology_hash": "wb_fake_method_hash"}, indent=2),
            encoding="utf-8",
        )
        (run_dir / "audit_chain_verification.json").write_text(
            json.dumps(
                {
                    "status": verify,
                    "events": 4,
                    "breaks": [],
                    "event_type_counts": {
                        "validation_run.start": 1,
                        "bias_battery.result": 1,
                        "drift.event": 1,
                        "validation_run.complete": 1,
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        db = run_dir / "workbench.db"
        db.write_bytes(b"")  # placeholder; verify unknown unless real chain
        return RunSnapshot(
            status=status,
            finding_title="AIR = 0.82 (sex)" if status != "failed" else "Validation exception",
            finding_subtitle=f"{self._preset_id} · review-support only",
            config_hash=config_hash,
            primary_report=str(report),
            verify_status=verify,
            verify_breaks=[] if verify == "PASS" else [{"index": 0, "reason": "fake break"}],
            extra={
                "workbench_db": str(db),
                "bias_battery_summary": str(run_dir / "bias_battery_summary.json"),
            },
        )

"""synth-fin CLI child pipeline: generate → validate → report."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from evidence_workbench.presets import get_generator_preset
from evidence_workbench.runners.base import (
    RunSnapshot,
    map_synth_overall,
    spawn_process_group,
    terminate_process_group,
)
from evidence_workbench.status import map_engine_status


class SynthFinRunner:
    def __init__(self, *, synth_fin_root: Path) -> None:
        self.synth_fin_root = synth_fin_root
        self._thread: threading.Thread | None = None
        self._snapshot = RunSnapshot(status="queued")
        self._lock = threading.Lock()
        self._proc: Any = None
        self._cancel = threading.Event()

    def start(self, preset_id: str, run_dir: Path) -> None:
        preset = get_generator_preset(preset_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._snapshot = RunSnapshot(status="running")
            self._cancel.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(preset, run_dir),
            daemon=True,
            name=f"synth-fin-{preset_id}",
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
                    finding_subtitle="Cancelled before terminal artifacts settled",
                )

    def _set(self, snap: RunSnapshot) -> None:
        with self._lock:
            self._snapshot = snap

    def _run(self, preset: Any, run_dir: Path) -> None:
        panel_dir = run_dir / "panel"
        validation_path = run_dir / "validation.json"
        report_path = run_dir / "report.html"
        try:
            gen_argv = self._uv_argv([
                "synth-fin",
                "generate",
                "--scenario",
                preset.scenario,
                "--bias-profile",
                preset.bias_profile,
                "--n",
                str(preset.n),
                "--seed",
                str(preset.seed),
                "--out",
                str(panel_dir),
            ])
            if self._cancel.is_set() or not self._exec(gen_argv):
                self._set_incomplete()
                return

            val_argv = self._uv_argv([
                "synth-fin",
                "validate",
                "--in",
                str(panel_dir),
                "--out",
                str(validation_path),
            ])
            if self._cancel.is_set() or not self._exec(val_argv, allow_nonzero=True):
                if self._cancel.is_set():
                    self._set_incomplete()
                    return
                # hard fail still may have written validation.json
                snap = self._read_terminal(panel_dir, validation_path, report_path, force_failed=True)
                self._set(snap)
                return

            if self._cancel.is_set():
                self._set_incomplete()
                return

            rep_argv = self._uv_argv([
                "synth-fin",
                "report",
                "--in",
                str(panel_dir),
                "--out",
                str(report_path),
            ])
            # validation.json lives in panel after validate if --out was panel-relative;
            # our --out is run_dir/validation.json — copy/symlink into panel for report.
            panel_validation = panel_dir / "validation.json"
            if validation_path.is_file() and not panel_validation.is_file():
                panel_validation.write_bytes(validation_path.read_bytes())

            if self._cancel.is_set() or not self._exec(rep_argv):
                if self._cancel.is_set():
                    self._set_incomplete()
                    return
                snap = self._read_terminal(panel_dir, validation_path, report_path, force_failed=True)
                self._set(snap)
                return

            self._set(self._read_terminal(panel_dir, validation_path, report_path))
        except Exception as exc:  # noqa: BLE001 — surface as failed snapshot
            self._set(
                RunSnapshot(
                    status="failed",
                    finding_title="Generator pipeline error",
                    finding_subtitle=str(exc),
                    error={"code": "runner_exception", "message": str(exc), "hint": "Check synth-fin CLI logs"},
                )
            )

    def _uv_argv(self, argv: list[str]) -> list[str]:
        """Prefer `uv run --directory <root>` so engine deps stay in synth-fin's env."""
        return ["uv", "run", "--directory", str(self.synth_fin_root), *argv]

    def _exec(self, argv: list[str], *, allow_nonzero: bool = False) -> bool:
        proc = spawn_process_group(argv, cwd=self.synth_fin_root)
        self._proc = proc
        stdout, stderr = proc.communicate()
        self._proc = None
        if self._cancel.is_set():
            return False
        if proc.returncode != 0 and not allow_nonzero:
            self._set(
                RunSnapshot(
                    status="failed",
                    finding_title="CLI step failed",
                    finding_subtitle=(stderr or stdout or "")[:500],
                    error={
                        "code": "cli_nonzero",
                        "message": f"{' '.join(argv)} exited {proc.returncode}",
                        "hint": stderr[:300] if stderr else "Inspect run directory artifacts",
                    },
                )
            )
            return False
        return True

    def _set_incomplete(self) -> None:
        self._set(
            RunSnapshot(
                status="incomplete",
                finding_title="Run incomplete",
                finding_subtitle="Cancelled before terminal artifacts settled",
            )
        )

    def _read_terminal(
        self,
        panel_dir: Path,
        validation_path: Path,
        report_path: Path,
        *,
        force_failed: bool = False,
    ) -> RunSnapshot:
        overall = "fail" if force_failed else "pass"
        pillars: list[dict[str, Any]] = []
        finding_title = "Generation complete"
        finding_subtitle = ""
        config_hash = None
        manifest_path = panel_dir / "manifest.json"
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                config_hash = manifest.get("config_hash")
                bias = manifest.get("bias") or {}
                if isinstance(bias, dict) and bias.get("profile") not in (None, "none"):
                    gap = bias.get("subgroup_gap_pp") or bias.get("gap_pp")
                    if gap is not None:
                        finding_title = f"Subgroup gap +{gap}pp"
                    finding_subtitle = str(bias.get("summary") or "manifest ground truth")
            except (json.JSONDecodeError, OSError):
                pass
        if validation_path.is_file():
            try:
                validation = json.loads(validation_path.read_text(encoding="utf-8"))
                overall = validation.get("overall_state", overall)
                pillar_blob = validation.get("pillars") or validation.get("pillar_results") or {}
                if isinstance(pillar_blob, dict):
                    for name, body in pillar_blob.items():
                        state = body.get("state") if isinstance(body, dict) else body
                        pillars.append({"name": str(name).title(), "state": map_engine_status(str(state))})
                bias = validation.get("bias") or {}
                if isinstance(bias, dict) and bias.get("subgroup_gap_pp") is not None:
                    finding_title = f"Subgroup gap +{bias['subgroup_gap_pp']}pp"
                    bq = bias.get("bottom_quartile_pct")
                    tq = bias.get("top_quartile_pct")
                    if bq is not None and tq is not None:
                        finding_subtitle = f"Bottom quartile {bq}% → top quartile {tq}% (manifest ground truth)"
            except (json.JSONDecodeError, OSError):
                overall = "fail"

        status = map_synth_overall(overall)
        if force_failed:
            status = "failed"
        primary = str(report_path) if report_path.is_file() else None
        # Prefer panel validation.json location for extra
        return RunSnapshot(
            status=status,
            finding_title=finding_title,
            finding_subtitle=finding_subtitle or None,
            config_hash=config_hash,
            primary_report=primary,
            pillars=pillars,
            extra={
                "validation_json": str(validation_path) if validation_path.is_file() else None,
                "manifest_json": str(manifest_path) if manifest_path.is_file() else None,
                "panel_dir": str(panel_dir),
            },
        )

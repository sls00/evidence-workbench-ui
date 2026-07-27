"""Slice B API: markdown report wrap, timeline, inspect allowlist."""

from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from evidence_workbench.run_index import IndexEntry, RunIndex


def _wait_terminal(client: TestClient, run_id: str) -> dict:
    for _ in range(80):
        snap = client.get(f"/api/runs/{run_id}").json()
        if snap["status"] in {"ok", "failed", "qualified", "incomplete"}:
            return snap
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} did not terminate")


def test_markdown_report_wrapped_as_html(client: TestClient):
    r = client.post("/api/runs", json={"home": "validation", "preset_id": "gc_full"})
    run_id = r.json()["run_id"]
    snap = _wait_terminal(client, run_id)
    assert snap["status"] in {"ok", "qualified"}
    assert snap.get("verify_status")  # B2: verify chip without Re-verify click
    rep = client.get(f"/api/runs/{run_id}/report")
    assert rep.status_code == 200
    assert "text/html" in rep.headers.get("content-type", "")
    assert b"Fake OCC report" in rep.content
    assert b"markdown (engine artifact)" in rep.content
    assert b"<pre class=\"md\">" in rep.content


def test_timeline_generator_from_manifest(client: TestClient):
    r = client.post("/api/runs", json={"home": "generator", "preset_id": "bias_demo_1k"})
    run_id = r.json()["run_id"]
    _wait_terminal(client, run_id)
    tl = client.get(f"/api/runs/{run_id}/timeline").json()
    assert tl["empty"] is False
    assert tl["source"] in {"panel/manifest.json", "manifest.json"}
    labels = [e["label"] for e in tl["events"]]
    assert "cli.parse" in labels
    assert "io.write" in labels


def test_timeline_validation_from_audit(client: TestClient):
    r = client.post("/api/runs", json={"home": "validation", "preset_id": "gc_full"})
    run_id = r.json()["run_id"]
    _wait_terminal(client, run_id)
    tl = client.get(f"/api/runs/{run_id}/timeline").json()
    assert tl["empty"] is False
    assert tl["source"] == "audit_chain_verification.json"
    assert any(e["label"] == "validation_run.complete" for e in tl["events"])


def test_timeline_empty_for_incomplete(client: TestClient):
    from evidence_workbench.runners import FakeRunner

    orch = client.app.state.orch
    original = orch._make_runner

    def hanging(home: str):
        return FakeRunner(home=home, hang=True, delay_seconds=30)

    orch._make_runner = hanging  # type: ignore[method-assign]
    try:
        r = client.post("/api/runs", json={"home": "generator", "preset_id": "bias_demo_1k"})
        run_id = r.json()["run_id"]
        c = client.post(f"/api/runs/{run_id}/cancel")
        assert c.json()["status"] == "incomplete"
        tl = client.get(f"/api/runs/{run_id}/timeline").json()
        assert tl["empty"] is True
        assert "incomplete" in (tl.get("honesty") or "").lower()
        insp = client.get(f"/api/runs/{run_id}/inspect").json()
        assert insp["empty"] is True
    finally:
        orch._make_runner = original  # type: ignore[method-assign]


def test_inspect_generator_allowlisted(client: TestClient):
    r = client.post("/api/runs", json={"home": "generator", "preset_id": "bias_demo_1k"})
    run_id = r.json()["run_id"]
    _wait_terminal(client, run_id)
    insp = client.get(f"/api/runs/{run_id}/inspect").json()
    assert insp["empty"] is False
    ids = {p["id"] for p in insp["panes"]}
    assert "pillars" in ids
    assert "bias_metrics" in ids
    sources = {p["source"] for p in insp["panes"]}
    assert sources <= {
        "validation.json",
        "panel/validation.json",
        "panel/manifest.json",
        "manifest.json",
    }


def test_inspect_validation_allowlisted(client: TestClient):
    r = client.post("/api/runs", json={"home": "validation", "preset_id": "gc_full"})
    run_id = r.json()["run_id"]
    _wait_terminal(client, run_id)
    insp = client.get(f"/api/runs/{run_id}/inspect").json()
    assert insp["empty"] is False
    ids = {p["id"] for p in insp["panes"]}
    assert "bias_battery" in ids
    assert "drift" in ids
    for pane in insp["panes"]:
        assert pane["source"] in {
            "bias_battery_summary.json",
            "drift_report.json",
            "audit_chain_verification.json",
            "translation_methodology_v1.json",
            "fidelity_validation_report.json",
        }


def test_timeline_path_confined(client: TestClient, settings, tmp_path: Path):
    """Poisoned symlink outside run dir must not be read as timeline source."""
    idx = RunIndex(settings.runs_root)
    idx.ensure_root()
    run_id = "20260727T000000Z-timeline1"
    run_dir = settings.runs_root / "synth-fin" / run_id
    run_dir.mkdir(parents=True)
    outside = tmp_path / "evil_manifest.json"
    outside.write_text('{"stages":[{"stage":"evil"}]}', encoding="utf-8")
    link = run_dir / "panel"
    try:
        link.symlink_to(tmp_path)
    except OSError:
        # If symlink blocked, still assert missing-artifacts honesty path
        pass
    entry = IndexEntry(
        run_id=run_id,
        namespace="synth-fin",
        preset_id="bias_demo_1k",
        created_at="2026-07-27T00:00:00+00:00",
        status="ok",
        config_hash=None,
        artifact_dir=str(run_dir),
        primary_report=None,
        home="generator",
        finding_title="x",
    )
    idx.append(entry)
    tl = client.get(f"/api/runs/{run_id}/timeline").json()
    # Either empty (no safe file) or events only from files under run_dir resolve
    if not tl["empty"]:
        for ev in tl["events"]:
            assert ev["label"] != "evil"

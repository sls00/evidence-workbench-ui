"""Unit + API smoke with fake runners (mandatory cancel + lock reclaim)."""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from evidence_workbench.locks import LockBusyError, NamespaceLock, try_acquire, release
from evidence_workbench.preflight import run_preflight
from evidence_workbench.run_index import IndexEntry, RunIndex, mint_run_id
from evidence_workbench.settings import Settings, resolve_runs_root
from evidence_workbench.status import map_engine_status


def test_mint_run_id_format():
    rid = mint_run_id()
    assert "T" in rid and rid.endswith(rid.split("-")[-1])
    assert len(rid.split("-")[-1]) == 8


def test_map_qualified_pass():
    assert map_engine_status("qualified_pass") == "qualified"
    assert map_engine_status("pass") == "ok"
    assert map_engine_status("fail") == "failed"


def test_resolve_runs_root_env(tmp_path: Path):
    p = tmp_path / "runs"
    assert resolve_runs_root({"EVIDENCE_RUNS_ROOT": str(p)}) == p.resolve()


def test_run_index_corrupt_line(runs_root: Path):
    idx = RunIndex(runs_root)
    idx.ensure_root()
    run_dir = runs_root / "synth-fin" / "r1"
    run_dir.mkdir(parents=True)
    good = IndexEntry(
        run_id="r1",
        namespace="synth-fin",
        preset_id="bias_demo_1k",
        created_at="2026-07-26T00:00:00Z",
        status="ok",
        config_hash="abc",
        artifact_dir=str(run_dir),
        primary_report=None,
        home="generator",
    )
    idx.append(good)
    with idx.path.open("a", encoding="utf-8") as fh:
        fh.write("{not json\n")
    result = idx.list(namespace="synth-fin")
    assert len(result.entries) == 1
    assert result.corrupt_lines == 1
    assert result.warnings


def test_lock_acquire_busy_and_stale_reclaim(runs_root: Path):
    lock = NamespaceLock(runs_root, "synth-fin", stale_seconds=0.05)
    info, reclaimed = try_acquire(lock, "run-a", pid=1)
    assert info.run_id == "run-a"
    assert reclaimed is None
    with pytest.raises(LockBusyError):
        try_acquire(lock, "run-b", pid=1)
    # Make heartbeat stale + dead pid
    time.sleep(0.06)
    info2, reclaimed2 = try_acquire(lock, "run-c", pid=999999)
    assert info2.run_id == "run-c"
    assert reclaimed2 is not None and reclaimed2.run_id == "run-a"
    release(lock, "run-c")


def test_preflight_warn_does_not_block(settings: Settings, monkeypatch, tmp_path: Path):
    # Disk warn path: force low disk with real (non-fake) preflight
    from dataclasses import replace

    import evidence_workbench.preflight as pf

    real = replace(settings, fake_runners=False, synth_fin_root=tmp_path / "nope")
    # Ensure runs root writable so disk check runs
    monkeypatch.setattr(pf, "_disk_free_mb", lambda _p: 100.0)
    monkeypatch.setattr(pf, "_import_ok", lambda _m: True)
    monkeypatch.setattr(pf, "_writable", lambda _p: True)
    # Provide a fake-looking synth root for seed check skip path — use blocker-free roots
    synth = tmp_path / "synth-fin"
    (synth / "src" / "synth_fin" / "seed").mkdir(parents=True)
    (synth / "src" / "synth_fin" / "generators").mkdir(parents=True)
    (synth / "src" / "synth_fin" / "generators" / "copula.py").write_text("#", encoding="utf-8")
    (synth / "pyproject.toml").write_text("[project]\nname='synth-fin'\n", encoding="utf-8")
    real = replace(real, synth_fin_root=synth)
    result = run_preflight(real, "generator")
    warns = [c for c in result.checks if c.status == "warn"]
    assert any(c.id == "disk" for c in warns)
    blockers = [c for c in result.checks if c.status == "blocker"]
    assert result.can_run == (len(blockers) == 0)
    assert result.can_run is True  # warn must not disable Run


def test_health(client: TestClient):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["fake_runners"] is True


def test_presets(client: TestClient):
    r = client.get("/api/presets", params={"home": "generator"})
    assert r.status_code == 200
    ids = [p["id"] for p in r.json()["presets"]]
    assert ids[0] == "bias_demo_1k"
    r2 = client.get("/api/presets", params={"home": "validation"})
    assert r2.json()["presets"][0]["id"] == "gc_full"


def test_post_202_poll_terminal(client: TestClient):
    r = client.post("/api/runs", json={"home": "generator", "preset_id": "bias_demo_1k"})
    assert r.status_code == 202
    run_id = r.json()["run_id"]
    terminal = None
    for _ in range(50):
        snap = client.get(f"/api/runs/{run_id}").json()
        if snap["status"] in {"ok", "failed", "qualified", "incomplete"}:
            terminal = snap
            break
        time.sleep(0.05)
    assert terminal is not None
    assert terminal["status"] in {"ok", "qualified"}
    assert terminal["finding_title"]
    assert terminal["pillars"]
    lib = client.get("/api/runs", params={"home": "generator"}).json()
    assert any(row["run_id"] == run_id for row in lib["runs"])


def test_cancel_incomplete_and_lock_free(client: TestClient, settings: Settings):
    """Mandatory smoke: cancel → incomplete; namespace lock released."""
    # Hang runner via monkeypatch FakeRunner
    from evidence_workbench.orchestrator import Orchestrator
    from evidence_workbench.runners import FakeRunner

    orch: Orchestrator = client.app.state.orch
    original = orch._make_runner

    def hanging(home: str):
        return FakeRunner(home=home, hang=True, delay_seconds=30)

    orch._make_runner = hanging  # type: ignore[method-assign]
    try:
        r = client.post("/api/runs", json={"home": "validation", "preset_id": "gc_full"})
        assert r.status_code == 202
        run_id = r.json()["run_id"]
        # Busy second run → 409
        busy = client.post("/api/runs", json={"home": "validation", "preset_id": "gc_full"})
        assert busy.status_code == 409
        # Cancel
        c = client.post(f"/api/runs/{run_id}/cancel")
        assert c.status_code == 200
        body = c.json()
        assert body["status"] == "incomplete"
        assert body["verify_status"] in {"unverifiable", "unknown", None} or body["verify_status"] == "unverifiable"
        assert body.get("verify_status") != "PASS"  # never fake PASS
        # Lock free — new run accepted
        r2 = client.post("/api/runs", json={"home": "validation", "preset_id": "gc_full"})
        assert r2.status_code == 202
        # cancel second hang too
        client.post(f"/api/runs/{r2.json()['run_id']}/cancel")
    finally:
        orch._make_runner = original  # type: ignore[method-assign]


def test_stale_lock_reclaim_allows_run(client: TestClient, settings: Settings):
    lock = NamespaceLock(settings.runs_root, "synth-fin", stale_seconds=0.01)
    try_acquire(lock, "orphan-run", pid=999999)
    time.sleep(0.02)
    # Force stale by rewriting heartbeat in past — is_stale also checks dead pid
    r = client.post("/api/runs", json={"home": "generator", "preset_id": "base_1k"})
    assert r.status_code == 202
    # Wait terminal
    run_id = r.json()["run_id"]
    for _ in range(50):
        if client.get(f"/api/runs/{run_id}").json()["status"] != "running":
            break
        time.sleep(0.05)


def test_report_path_traversal_rejected(client: TestClient, settings: Settings):
    r = client.post("/api/runs", json={"home": "generator", "preset_id": "bias_demo_1k"})
    run_id = r.json()["run_id"]
    for _ in range(50):
        snap = client.get(f"/api/runs/{run_id}").json()
        if snap["status"] != "running":
            break
        time.sleep(0.05)
    # Poison primary_report via index rewrite
    idx = RunIndex(settings.runs_root)
    entry = idx.get(run_id)
    assert entry is not None
    # Append a malicious second entry pointing outside
    evil_dir = settings.runs_root / "synth-fin" / "evil"
    evil_dir.mkdir(parents=True, exist_ok=True)
    # Create symlink escape attempt inside run dir
    run_dir = Path(entry.artifact_dir)
    outside = settings.runs_root.parent / "secret.txt"
    outside.write_text("nope", encoding="utf-8")
    link = run_dir / "escape.html"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink not permitted")
    # Manually set report via active poll path — use orch.report_path allowlist
    orch = client.app.state.orch
    with pytest.raises((PermissionError, FileNotFoundError, ValueError)):
        # If symlink resolves outside run dir under runs_root, relative_to(runs_root) may still pass.
        # Eng plan: path confined to run dir — assert under run_dir.
        path = link.resolve()
        orch._assert_under_run(run_dir, path)


def test_reopen_missing_primary_report(client: TestClient, settings: Settings):
    idx = RunIndex(settings.runs_root)
    idx.ensure_root()
    run_dir = settings.runs_root / "ai-mrg-bench" / "20260726T000000Z-deadbeef"
    run_dir.mkdir(parents=True)
    entry = IndexEntry(
        run_id="20260726T000000Z-deadbeef",
        namespace="ai-mrg-bench",
        preset_id="gc_full",
        created_at="2026-07-26T00:00:00+00:00",
        status="ok",
        config_hash=None,
        artifact_dir=str(run_dir),
        primary_report=str(run_dir / "missing.md"),
        home="validation",
        finding_title="ghost",
    )
    idx.append(entry)
    snap = client.get("/api/runs/20260726T000000Z-deadbeef").json()
    assert snap["artifacts_missing"] is True
    lib = client.get("/api/runs", params={"home": "validation"}).json()
    row = next(r for r in lib["runs"] if r["run_id"] == "20260726T000000Z-deadbeef")
    assert row["artifacts_missing"] is True


def test_qualified_mapping_via_fake(client: TestClient):
    from evidence_workbench.runners import FakeRunner

    orch = client.app.state.orch
    original = orch._make_runner

    def qualified(home: str):
        return FakeRunner(home=home, outcome="qualified", delay_seconds=0.05)

    orch._make_runner = qualified  # type: ignore[method-assign]
    try:
        r = client.post("/api/runs", json={"home": "generator", "preset_id": "bias_demo_1k"})
        run_id = r.json()["run_id"]
        for _ in range(50):
            snap = client.get(f"/api/runs/{run_id}").json()
            if snap["status"] != "running":
                assert snap["status"] == "qualified"
                return
            time.sleep(0.05)
        pytest.fail("did not terminate")
    finally:
        orch._make_runner = original  # type: ignore[method-assign]


def test_report_served(client: TestClient):
    r = client.post("/api/runs", json={"home": "generator", "preset_id": "bias_demo_1k"})
    run_id = r.json()["run_id"]
    for _ in range(50):
        snap = client.get(f"/api/runs/{run_id}").json()
        if snap["status"] != "running":
            break
        time.sleep(0.05)
    rep = client.get(f"/api/runs/{run_id}/report")
    assert rep.status_code == 200
    assert b"Fake synth-fin report" in rep.content
    assert b"embed-body" in rep.content
    assert b"#E8EAED" in rep.content
    assert "inline" in rep.headers.get("content-disposition", "").lower()

    dl = client.get(f"/api/runs/{run_id}/report", params={"download": True})
    assert dl.status_code == 200
    assert b"embed-body" not in dl.content
    assert "attachment" in dl.headers.get("content-disposition", "").lower()


def test_default_bind_host_respects_explicit():
    from evidence_workbench.netutil import default_bind_host, public_urls

    assert default_bind_host(explicit="127.0.0.1") == "127.0.0.1"
    assert default_bind_host(explicit="0.0.0.0") == "0.0.0.0"
    urls = public_urls(host="0.0.0.0", port=8765, home="generator")
    assert urls[0] == "http://127.0.0.1:8765/?home=generator"

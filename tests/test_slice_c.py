"""Slice C API: same-home run compare."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from evidence_workbench.runners import FakeRunner


def _wait_terminal(client: TestClient, run_id: str) -> dict:
    for _ in range(80):
        snap = client.get(f"/api/runs/{run_id}").json()
        if snap["status"] in {"ok", "failed", "qualified", "incomplete"}:
            return snap
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} did not terminate")


def _start(client: TestClient, home: str, preset_id: str) -> str:
    r = client.post("/api/runs", json={"home": home, "preset_id": preset_id})
    assert r.status_code == 202
    return r.json()["run_id"]


def test_compare_generator_two_presets(client: TestClient):
    left_id = _start(client, "generator", "bias_demo_1k")
    _wait_terminal(client, left_id)
    right_id = _start(client, "generator", "base_1k")
    _wait_terminal(client, right_id)

    cmp = client.get(
        "/api/runs/compare",
        params={"home": "generator", "left": left_id, "right": right_id},
    )
    assert cmp.status_code == 200
    body = cmp.json()
    assert body["home"] == "generator"
    assert body["artifact_label"] == "validation.json"
    assert body["left"]["preset_id"] == "bias_demo_1k"
    assert body["right"]["preset_id"] == "base_1k"
    assert body["left"]["config_hash"] != body["right"]["config_hash"]
    assert body["identical"] is False
    assert "subgroup_gap_pp" in body["diff_text"]


def test_compare_validation_with_verify_status(client: TestClient):
    left_id = _start(client, "validation", "gc_full")
    _wait_terminal(client, left_id)
    right_id = _start(client, "validation", "gc_ca_overlay")
    _wait_terminal(client, right_id)

    cmp = client.get(
        "/api/runs/compare",
        params={"home": "validation", "left": left_id, "right": right_id},
    )
    assert cmp.status_code == 200
    body = cmp.json()
    assert body["artifact_label"] == "bias_battery_summary.json"
    assert body["left"]["verify_status"] == "PASS"
    assert body["right"]["verify_status"] == "PASS"
    assert body["identical"] is False
    assert "reference_group" in body["diff_text"]


def test_compare_rejects_same_run(client: TestClient):
    run_id = _start(client, "generator", "bias_demo_1k")
    _wait_terminal(client, run_id)
    r = client.get(
        "/api/runs/compare",
        params={"home": "generator", "left": run_id, "right": run_id},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["code"] == "same_run"


def test_compare_rejects_cross_home(client: TestClient):
    gen_id = _start(client, "generator", "bias_demo_1k")
    val_id = _start(client, "validation", "gc_full")
    _wait_terminal(client, gen_id)
    _wait_terminal(client, val_id)

    r = client.get(
        "/api/runs/compare",
        params={"home": "generator", "left": gen_id, "right": val_id},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["code"] == "cross_home"


def test_compare_empty_for_incomplete(client: TestClient):
    orch = client.app.state.orch
    original = orch._make_runner

    def hanging(home: str):
        return FakeRunner(home=home, hang=True, delay_seconds=30)

    orch._make_runner = hanging  # type: ignore[method-assign]
    try:
        left_id = _start(client, "generator", "bias_demo_1k")
        client.post(f"/api/runs/{left_id}/cancel")
        _wait_terminal(client, left_id)
        orch._make_runner = original  # type: ignore[method-assign]
        right_id = _start(client, "generator", "base_1k")
        _wait_terminal(client, right_id)

        cmp = client.get(
            "/api/runs/compare",
            params={"home": "generator", "left": left_id, "right": right_id},
        )
        assert cmp.status_code == 200
        body = cmp.json()
        assert body["empty"] is True
        assert "terminal" in (body.get("honesty") or "").lower()
    finally:
        orch._make_runner = original  # type: ignore[method-assign]


def test_compare_not_found(client: TestClient):
    run_id = _start(client, "generator", "bias_demo_1k")
    _wait_terminal(client, run_id)
    r = client.get(
        "/api/runs/compare",
        params={"home": "generator", "left": run_id, "right": "nonexistent-run-id"},
    )
    assert r.status_code == 404

"""Shared pytest fixtures for Evidence Workbench tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from evidence_workbench.app import create_app
from evidence_workbench.settings import Settings, load_settings


@pytest.fixture()
def runs_root(tmp_path: Path) -> Path:
    root = tmp_path / ".evidence-runs"
    root.mkdir()
    return root


@pytest.fixture()
def settings(runs_root: Path) -> Settings:
    base = load_settings(env={"EVIDENCE_RUNS_ROOT": str(runs_root), "EVIDENCE_FAKE_RUNNERS": "1"})
    return replace(base, runs_root=runs_root, fake_runners=True)


@pytest.fixture()
def client(settings: Settings) -> TestClient:
    app = create_app(settings)
    with TestClient(app) as c:
        yield c

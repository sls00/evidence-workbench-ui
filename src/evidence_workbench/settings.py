"""Roots, runs dir, and auto-discover (eng plan P4 / root discover)."""

from __future__ import annotations

import importlib.util
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

DEFAULT_RUNS_ROOT = Path(".evidence-runs")
HOMES = ("generator", "validation")
NAMESPACES = {
    "generator": "synth-fin",
    "validation": "ai-mrg-bench",
}


@dataclass(frozen=True, slots=True)
class Settings:
    runs_root: Path
    synth_fin_root: Path | None
    ai_mrg_bench_root: Path | None
    host: str = "127.0.0.1"
    port: int = 8765
    fake_runners: bool = False

    def namespace_for(self, home: str) -> str:
        if home not in NAMESPACES:
            raise ValueError(f"unknown home: {home}")
        return NAMESPACES[home]

    def root_for(self, home: str) -> Path | None:
        if home == "generator":
            return self.synth_fin_root
        if home == "validation":
            return self.ai_mrg_bench_root
        raise ValueError(f"unknown home: {home}")


def _looks_like_synth_fin(path: Path) -> bool:
    return (path / "pyproject.toml").is_file() and (path / "src" / "synth_fin").is_dir()


def _looks_like_ai_mrg_bench(path: Path) -> bool:
    return (
        (path / "pyproject.toml").is_file()
        and (path / "src" / "workbench").is_dir()
        and (path / "configs").is_dir()
    )


def _walk_parents_for_root(origin: Path, predicate) -> Path | None:
    cur = origin.resolve()
    for parent in [cur, *cur.parents]:
        if predicate(parent):
            return parent
    return None


def _discover_from_import(module_name: str, predicate) -> Path | None:
    spec = importlib.util.find_spec(module_name)
    if spec is None or spec.origin is None:
        return None
    return _walk_parents_for_root(Path(spec.origin), predicate)


def _discover_from_siblings() -> tuple[Path | None, Path | None]:
    """If evid-wb-ui parent contains sibling dirs, use those."""
    here = Path(__file__).resolve()
    # .../evid-wb-ui/src/evidence_workbench/settings.py → portfolio/
    for parent in here.parents:
        synth = parent / "synth-fin"
        bench = parent / "ai-mrg-bench"
        evid = parent / "evid-wb-ui"
        if evid.is_dir() and _looks_like_synth_fin(synth) and _looks_like_ai_mrg_bench(bench):
            return synth, bench
    return None, None


def resolve_synth_fin_root(env: dict[str, str] | None = None) -> Path | None:
    env = env if env is not None else os.environ
    if raw := env.get("SYNTH_FIN_ROOT"):
        p = Path(raw).expanduser().resolve()
        return p if _looks_like_synth_fin(p) else None
    if ws := env.get("EVIDENCE_WORKSPACE"):
        p = Path(ws).expanduser().resolve() / "synth-fin"
        if _looks_like_synth_fin(p):
            return p
    found = _discover_from_import("synth_fin", _looks_like_synth_fin)
    if found:
        return found
    sibling, _ = _discover_from_siblings()
    return sibling


def resolve_ai_mrg_bench_root(env: dict[str, str] | None = None) -> Path | None:
    env = env if env is not None else os.environ
    if raw := env.get("AI_MRG_BENCH_ROOT"):
        p = Path(raw).expanduser().resolve()
        return p if _looks_like_ai_mrg_bench(p) else None
    if ws := env.get("EVIDENCE_WORKSPACE"):
        p = Path(ws).expanduser().resolve() / "ai-mrg-bench"
        if _looks_like_ai_mrg_bench(p):
            return p
    found = _discover_from_import("workbench", _looks_like_ai_mrg_bench)
    if found:
        return found
    _, sibling = _discover_from_siblings()
    return sibling


def resolve_runs_root(env: dict[str, str] | None = None, cwd: Path | None = None) -> Path:
    env = env if env is not None else os.environ
    cwd = cwd or Path.cwd()
    if raw := env.get("EVIDENCE_RUNS_ROOT"):
        return Path(raw).expanduser().resolve()
    return (cwd / DEFAULT_RUNS_ROOT).resolve()


def load_settings(
    *,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> Settings:
    env = env if env is not None else dict(os.environ)
    fake = env.get("EVIDENCE_FAKE_RUNNERS", "").lower() in {"1", "true", "yes"}
    return Settings(
        runs_root=resolve_runs_root(env, cwd),
        synth_fin_root=resolve_synth_fin_root(env),
        ai_mrg_bench_root=resolve_ai_mrg_bench_root(env),
        host=host,
        port=port,
        fake_runners=fake,
    )


def which_evidence_workbench() -> str | None:
    return shutil.which("evidence-workbench")

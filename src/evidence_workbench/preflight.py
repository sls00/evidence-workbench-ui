"""Preflight matrix with structured {code, message, hint} envelope."""

from __future__ import annotations

import importlib.util
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from evidence_workbench.settings import Settings

Severity = Literal["blocker", "warn", "ok"]


@dataclass(slots=True)
class PreflightError:
    code: str
    message: str
    hint: str


@dataclass(slots=True)
class PreflightCheck:
    id: str
    label: str
    severity: Severity
    status: Literal["ok", "warn", "blocker"]
    error: PreflightError | None = None


@dataclass(slots=True)
class PreflightResult:
    home: str
    checks: list[PreflightCheck]
    can_run: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "ok" if self.can_run else "blocked",
            "home": self.home,
            "can_run": self.can_run,
            "checks": [
                {
                    "id": c.id,
                    "label": c.label,
                    "severity": c.severity,
                    "status": c.status,
                    "error": asdict(c.error) if c.error else None,
                }
                for c in self.checks
            ],
            "error": _first_blocker(self.checks),
        }


def _first_blocker(checks: list[PreflightCheck]) -> dict[str, str] | None:
    for c in checks:
        if c.status == "blocker" and c.error:
            return asdict(c.error)
    return None


def _import_ok(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def _disk_free_mb(path: Path) -> float | None:
    try:
        path.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(path)
        return usage.free / (1024 * 1024)
    except OSError:
        return None


def _is_lfs_pointer(path: Path) -> bool:
    if not path.is_file():
        return True
    if path.stat().st_size < 200:
        try:
            head = path.read_text(encoding="utf-8", errors="ignore")[:120]
        except OSError:
            return True
        return "git-lfs.github.com/spec" in head or head.startswith("version https://git-lfs")
    return False


def _writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def run_preflight(settings: Settings, home: str) -> PreflightResult:
    if settings.fake_runners:
        # CI / demo without engines — all checks ok so chrome can exercise Run.
        return PreflightResult(
            home=home,
            checks=[
                _ok("fake_runners", "fake runners (CI)"),
                _ok("runs_root", "runs root writable")
                if _writable(settings.runs_root)
                else _blocker(
                    "runs_root",
                    "runs root writable",
                    "runs_root_unwritable",
                    f"Cannot write to {settings.runs_root}",
                    "export EVIDENCE_RUNS_ROOT=…",
                ),
            ],
            can_run=_writable(settings.runs_root),
        )

    checks: list[PreflightCheck] = []

    if home == "generator":
        checks.append(
            _check_import(
                "synth_fin",
                "uv/python import (synth_fin)",
                cli_name="synth-fin",
                root=settings.synth_fin_root,
            )
        )
        checks.append(_check_runs_root(settings))
        checks.append(_check_synth_root(settings))
        checks.append(_check_seed_copula(settings))
        checks.append(_check_disk(settings))
    elif home == "validation":
        checks.append(
            _check_import(
                "workbench",
                "uv/python import (workbench)",
                cli_name="workbench",
                root=settings.ai_mrg_bench_root,
            )
        )
        checks.append(_check_runs_root(settings))
        checks.append(_check_bench_root(settings))
        checks.append(_check_lfs_models(settings))
        checks.append(_check_fixture_hashes(settings))
        checks.append(_check_disk(settings))
    else:
        raise ValueError(f"unknown home: {home}")

    can_run = all(c.status != "blocker" for c in checks)
    return PreflightResult(home=home, checks=checks, can_run=can_run)


def _ok(id_: str, label: str) -> PreflightCheck:
    return PreflightCheck(id=id_, label=label, severity="ok", status="ok")


def _blocker(id_: str, label: str, code: str, message: str, hint: str) -> PreflightCheck:
    return PreflightCheck(
        id=id_,
        label=label,
        severity="blocker",
        status="blocker",
        error=PreflightError(code=code, message=message, hint=hint),
    )


def _warn(id_: str, label: str, code: str, message: str, hint: str) -> PreflightCheck:
    return PreflightCheck(
        id=id_,
        label=label,
        severity="warn",
        status="warn",
        error=PreflightError(code=code, message=message, hint=hint),
    )


def _check_import(module: str, label: str, *, cli_name: str, root: Path | None) -> PreflightCheck:
    """Import preferred; root+CLI acceptable when engines live in sibling envs."""
    if _import_ok(module):
        return _ok(f"import_{module}", label)
    if root is not None and root.is_dir() and shutil.which("uv"):
        return _ok(f"import_{module}", f"{label} (uv run @ root)")
    if shutil.which(cli_name):
        return _ok(f"import_{module}", f"{label} (PATH {cli_name})")
    return _blocker(
        f"import_{module}",
        label,
        "import_missing",
        f"Python package '{module}' is not importable and no root/CLI fallback",
        f"export root env + ensure `uv` works in sibling repo, or install `{cli_name}` on PATH.",
    )


def _check_runs_root(settings: Settings) -> PreflightCheck:
    label = "runs root writable"
    if _writable(settings.runs_root):
        return _ok("runs_root", label)
    return _blocker(
        "runs_root",
        label,
        "runs_root_unwritable",
        f"Cannot write to EVIDENCE_RUNS_ROOT ({settings.runs_root})",
        "export EVIDENCE_RUNS_ROOT=/path/you/can/write && mkdir -p \"$EVIDENCE_RUNS_ROOT\"",
    )


def _check_synth_root(settings: Settings) -> PreflightCheck:
    label = "synth-fin root"
    if settings.synth_fin_root and settings.synth_fin_root.is_dir():
        return _ok("synth_fin_root", label)
    return _blocker(
        "synth_fin_root",
        label,
        "root_missing",
        "SYNTH_FIN_ROOT not found / invalid",
        "export SYNTH_FIN_ROOT=/path/to/synth-fin  # needs pyproject.toml + src/synth_fin",
    )


def _check_bench_root(settings: Settings) -> PreflightCheck:
    label = "ai-mrg-bench root"
    if settings.ai_mrg_bench_root and settings.ai_mrg_bench_root.is_dir():
        return _ok("ai_mrg_bench_root", label)
    return _blocker(
        "ai_mrg_bench_root",
        label,
        "root_missing",
        "AI_MRG_BENCH_ROOT not found / invalid",
        "export AI_MRG_BENCH_ROOT=/path/to/ai-mrg-bench  # needs pyproject.toml + src/workbench + configs/",
    )


def _check_seed_copula(settings: Settings) -> PreflightCheck:
    label = "seed/copula"
    root = settings.synth_fin_root
    if root is None:
        return _blocker(
            "seed_copula",
            label,
            "seed_unavailable",
            "Cannot check seed/copula without synth-fin root",
            "Fix SYNTH_FIN_ROOT first (see M0 seed docs in synth-fin).",
        )
    seed_pkg = root / "src" / "synth_fin" / "seed"
    copula = root / "src" / "synth_fin" / "generators" / "copula.py"
    if seed_pkg.is_dir() and copula.is_file():
        return _ok("seed_copula", label)
    return _blocker(
        "seed_copula",
        label,
        "seed_unavailable",
        "Copula/seed package missing under synth-fin",
        "See synth-fin M0_KICKOFF.md — ensure seed priors and generators/copula.py are present.",
    )


def _check_lfs_models(settings: Settings) -> PreflightCheck:
    label = "LFS models"
    root = settings.ai_mrg_bench_root
    if root is None:
        return _blocker(
            "lfs_models",
            label,
            "lfs_missing",
            "Cannot check models without ai-mrg-bench root",
            "export AI_MRG_BENCH_ROOT=… then `git lfs pull` in that repo.",
        )
    models = [
        root / "models" / "german-credit-xgb-v1.2.joblib",
        root / "models" / "synth-fin-cre-xgb-v1.0.joblib",
    ]
    missing = [m for m in models if _is_lfs_pointer(m) or not m.is_file()]
    if not missing:
        return _ok("lfs_models", label)
    names = ", ".join(m.name for m in missing)
    return _blocker(
        "lfs_models",
        label,
        "lfs_missing",
        f"Model file(s) missing or still LFS pointers: {names}",
        f"cd {root} && git lfs pull",
    )


def _check_fixture_hashes(settings: Settings) -> PreflightCheck:
    label = "fixture hash verify"
    root = settings.ai_mrg_bench_root
    if root is None:
        return _blocker(
            "fixture_hashes",
            label,
            "fixture_hash_fail",
            "Cannot verify fixtures without ai-mrg-bench root",
            "export AI_MRG_BENCH_ROOT=… and run scripts/check_fixture_hashes.sh",
        )
    script = root / "scripts" / "check_fixture_hashes.sh"
    manifests = list((root / "manifests").glob("*_fixture_manifest.yaml")) if (root / "manifests").is_dir() else []
    if not script.is_file():
        return _blocker(
            "fixture_hashes",
            label,
            "fixture_hash_fail",
            "check_fixture_hashes.sh missing",
            f"Restore {script} from ai-mrg-bench bootstrap docs.",
        )
    if not manifests:
        # Script exits 0 with SKIP when no manifests — treat as warn, not blocker for Slice A empty bootstrap
        return _warn(
            "fixture_hashes",
            label,
            "fixture_manifest_absent",
            "No fixture manifests yet (bootstrap may be pending)",
            f"cd {root} && bash scripts/check_fixture_hashes.sh  # after fixture bootstrap",
        )
    # Lightweight presence: data dir + at least one manifest
    data = root / "data"
    if data.is_dir() and any(data.iterdir()):
        return _ok("fixture_hashes", label)
    return _blocker(
        "fixture_hashes",
        label,
        "fixture_hash_fail",
        "Fixture data directory empty or missing",
        f"cd {root} && bash scripts/bootstrap_german_credit_fixtures.py (or project bootstrap docs)",
    )


def _check_disk(settings: Settings) -> PreflightCheck:
    label = "disk space"
    free = _disk_free_mb(settings.runs_root)
    if free is None:
        return _warn(
            "disk",
            label,
            "disk_unknown",
            "Could not measure free disk",
            "Ensure EVIDENCE_RUNS_ROOT is on a mounted volume with free space.",
        )
    if free < 500:
        return _warn(
            "disk",
            label,
            "disk_low",
            f"Only {free:.0f} MB free under runs root",
            "Free disk space or point EVIDENCE_RUNS_ROOT elsewhere. Run still enabled.",
        )
    return _ok("disk", label)

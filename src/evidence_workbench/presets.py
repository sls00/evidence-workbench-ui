"""Locked Slice A preset catalogs (office-hours SoT)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

Home = Literal["generator", "validation"]


@dataclass(frozen=True, slots=True)
class GeneratorPreset:
    id: str
    label: str
    scenario: str
    bias_profile: str
    n: int
    seed: int
    default: bool = False

    def summary(self) -> str:
        return f"{self.id} · n={self.n} · seed={self.seed}"


@dataclass(frozen=True, slots=True)
class ValidationPreset:
    id: str
    label: str
    config_relpath: str
    default: bool = False
    needs_lfs_model: bool = True

    def summary(self) -> str:
        return f"{self.id} · {self.config_relpath}"


GENERATOR_PRESETS: tuple[GeneratorPreset, ...] = (
    GeneratorPreset(
        id="bias_demo_1k",
        label="Bias demo (1k)",
        scenario="base",
        bias_profile="proxy_discrimination_mild",
        n=1000,
        seed=42,
        default=True,
    ),
    GeneratorPreset(
        id="base_1k",
        label="Base (1k)",
        scenario="base",
        bias_profile="none",
        n=1000,
        seed=42,
    ),
    GeneratorPreset(
        id="rate_shock_1k",
        label="Rate shock 200bp (1k)",
        scenario="rate_shock_200bp",
        bias_profile="none",
        n=1000,
        seed=42,
    ),
)

VALIDATION_PRESETS: tuple[ValidationPreset, ...] = (
    ValidationPreset(
        id="gc_full",
        label="German Credit full",
        config_relpath="configs/german_credit_full.yaml",
        default=True,
    ),
    ValidationPreset(
        id="gc_ca_overlay",
        label="German Credit CA overlay",
        config_relpath="configs/german_credit_ca_overlay.yaml",
    ),
    ValidationPreset(
        id="cre_p5",
        label="Synth-fin CRE P5 (committed fixture)",
        config_relpath="configs/synth_fin_cre_baseline.yaml",
    ),
)


def presets_for(home: Home) -> list[dict[str, Any]]:
    if home == "generator":
        return [asdict(p) | {"summary": p.summary()} for p in GENERATOR_PRESETS]
    if home == "validation":
        return [asdict(p) | {"summary": p.summary()} for p in VALIDATION_PRESETS]
    raise ValueError(f"unknown home: {home}")


def default_preset_id(home: Home) -> str:
    if home == "generator":
        return next(p.id for p in GENERATOR_PRESETS if p.default)
    return next(p.id for p in VALIDATION_PRESETS if p.default)


def get_generator_preset(preset_id: str) -> GeneratorPreset:
    for p in GENERATOR_PRESETS:
        if p.id == preset_id:
            return p
    raise KeyError(preset_id)


def get_validation_preset(preset_id: str) -> ValidationPreset:
    for p in VALIDATION_PRESETS:
        if p.id == preset_id:
            return p
    raise KeyError(preset_id)

"""Read-only post-run artifact views (timeline + inspect). No shadow metrics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Allowlisted relative paths under a run dir (Slice B — office-hours table).
GENERATOR_TIMELINE_CANDIDATES = (
    "panel/manifest.json",
    "manifest.json",
)
VALIDATION_TIMELINE_CANDIDATES = (
    "audit_chain_verification.json",
)

GENERATOR_INSPECT_FILES = (
    "validation.json",
    "panel/validation.json",
    "panel/manifest.json",
    "manifest.json",
)
VALIDATION_INSPECT_FILES = (
    "bias_battery_summary.json",
    "drift_report.json",
    "audit_chain_verification.json",
    "translation_methodology_v1.json",
    "fidelity_validation_report.json",
)


def _safe_rel(run_dir: Path, rel: str) -> Path | None:
    run_dir = run_dir.resolve()
    path = (run_dir / rel).resolve()
    try:
        path.relative_to(run_dir)
    except ValueError:
        return None
    return path if path.is_file() else None


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def build_timeline(
    *,
    run_id: str,
    home: str,
    status: str,
    run_dir: Path,
) -> dict[str, Any]:
    if status == "incomplete" or status in {"running", "queued", "accepted"}:
        return {
            "run_id": run_id,
            "home": home,
            "status": status,
            "empty": True,
            "source": None,
            "events": [],
            "honesty": (
                "No timeline — run incomplete or cancelled before terminal artifacts settled."
                if status == "incomplete"
                else "Timeline available after the run reaches a terminal status."
            ),
        }

    if home == "generator":
        return _generator_timeline(run_id, home, status, run_dir)
    return _validation_timeline(run_id, home, status, run_dir)


def _generator_timeline(
    run_id: str, home: str, status: str, run_dir: Path
) -> dict[str, Any]:
    for rel in GENERATOR_TIMELINE_CANDIDATES:
        path = _safe_rel(run_dir, rel)
        if path is None:
            continue
        data = _read_json(path)
        if not isinstance(data, dict):
            continue
        stages = data.get("stages")
        if not isinstance(stages, list) or not stages:
            continue
        events = []
        for i, stage in enumerate(stages):
            if not isinstance(stage, dict):
                continue
            name = str(stage.get("stage") or stage.get("name") or f"stage_{i}")
            events.append(
                {
                    "id": name,
                    "label": name,
                    "detail": {k: v for k, v in stage.items() if k not in {"stage", "name"}},
                    "index": i,
                }
            )
        return {
            "run_id": run_id,
            "home": home,
            "status": status,
            "empty": len(events) == 0,
            "source": rel,
            "events": events,
            "honesty": None if events else "Manifest present but no stages recorded.",
        }
    return {
        "run_id": run_id,
        "home": home,
        "status": status,
        "empty": True,
        "source": None,
        "events": [],
        "honesty": "No manifest stages on disk for this run.",
    }


def _validation_timeline(
    run_id: str, home: str, status: str, run_dir: Path
) -> dict[str, Any]:
    for rel in VALIDATION_TIMELINE_CANDIDATES:
        path = _safe_rel(run_dir, rel)
        if path is None:
            continue
        data = _read_json(path)
        if not isinstance(data, dict):
            continue
        events: list[dict[str, Any]] = []
        counts = data.get("event_type_counts")
        if isinstance(counts, dict) and counts:
            for i, (etype, count) in enumerate(sorted(counts.items())):
                events.append(
                    {
                        "id": etype,
                        "label": etype,
                        "detail": {"count": count},
                        "index": i,
                    }
                )
        # Prefer ordered summary when present
        if isinstance(data.get("events"), list):
            ordered = []
            for i, ev in enumerate(data["events"]):
                if isinstance(ev, dict):
                    ordered.append(
                        {
                            "id": str(ev.get("type") or ev.get("event_type") or f"event_{i}"),
                            "label": str(ev.get("type") or ev.get("event_type") or f"event_{i}"),
                            "detail": {k: v for k, v in ev.items() if k not in {"type", "event_type"}},
                            "index": i,
                        }
                    )
            if ordered:
                events = ordered
        return {
            "run_id": run_id,
            "home": home,
            "status": status,
            "empty": len(events) == 0,
            "source": rel,
            "events": events,
            "verify_status": data.get("status"),
            "honesty": None if events else "Verification JSON present but no audit events listed.",
        }
    return {
        "run_id": run_id,
        "home": home,
        "status": status,
        "empty": True,
        "source": None,
        "events": [],
        "honesty": "No audit verification artifact on disk for this run.",
    }


def build_inspect(
    *,
    run_id: str,
    home: str,
    status: str,
    run_dir: Path,
) -> dict[str, Any]:
    if status == "incomplete" or status in {"running", "queued", "accepted"}:
        return {
            "run_id": run_id,
            "home": home,
            "status": status,
            "empty": True,
            "panes": [],
            "honesty": (
                "No metric inspect — run incomplete or cancelled before terminal artifacts settled."
                if status == "incomplete"
                else "Inspect available after the run reaches a terminal status."
            ),
        }

    if home == "generator":
        panes = _generator_inspect(run_dir)
    else:
        panes = _validation_inspect(run_dir)

    return {
        "run_id": run_id,
        "home": home,
        "status": status,
        "empty": len(panes) == 0,
        "panes": panes,
        "honesty": None if panes else "No allowlisted inspect artifacts on disk for this run.",
    }


def _fields_from_mapping(data: dict[str, Any], keys: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key in keys:
        if key in data:
            out.append({"key": key, "value": data[key]})
    return out


def _generator_inspect(run_dir: Path) -> list[dict[str, Any]]:
    panes: list[dict[str, Any]] = []
    validation = None
    validation_rel = None
    for rel in ("validation.json", "panel/validation.json"):
        path = _safe_rel(run_dir, rel)
        if path is None:
            continue
        data = _read_json(path)
        if isinstance(data, dict):
            validation = data
            validation_rel = rel
            break

    if validation is not None and validation_rel is not None:
        pillars = validation.get("pillars")
        if isinstance(pillars, dict):
            fields = []
            for name, body in pillars.items():
                state = body.get("state") if isinstance(body, dict) else body
                fields.append({"key": name, "value": state})
            if fields:
                panes.append(
                    {
                        "id": "pillars",
                        "title": "Pillars",
                        "source": validation_rel,
                        "fields": fields,
                    }
                )
        bias = validation.get("bias")
        if isinstance(bias, dict) and bias:
            panes.append(
                {
                    "id": "bias_metrics",
                    "title": "Bias metrics",
                    "source": validation_rel,
                    "fields": [{"key": k, "value": v} for k, v in bias.items()],
                }
            )
        overall = validation.get("overall_state")
        if overall is not None:
            panes.append(
                {
                    "id": "overall",
                    "title": "Overall",
                    "source": validation_rel,
                    "fields": [{"key": "overall_state", "value": overall}],
                }
            )

    for rel in ("panel/manifest.json", "manifest.json"):
        path = _safe_rel(run_dir, rel)
        if path is None:
            continue
        data = _read_json(path)
        if not isinstance(data, dict):
            continue
        fields = _fields_from_mapping(
            data,
            ["config_hash", "output_checksum", "package_version", "seed_source", "bias_profile"],
        )
        if fields:
            panes.append(
                {
                    "id": "manifest",
                    "title": "Manifest tokens",
                    "source": rel,
                    "fields": fields,
                }
            )
        break

    return panes


def _validation_inspect(run_dir: Path) -> list[dict[str, Any]]:
    panes: list[dict[str, Any]] = []

    bias_path = _safe_rel(run_dir, "bias_battery_summary.json")
    if bias_path is not None:
        data = _read_json(bias_path)
        if isinstance(data, dict):
            keys = [
                "status",
                "protected_attribute",
                "reference_group",
                "jurisdiction_frame",
                "run_id",
                "aequitas_pin",
            ]
            fields = _fields_from_mapping(data, keys)
            if "layers" in data:
                fields.append({"key": "layers", "value": data["layers"]})
            if fields:
                panes.append(
                    {
                        "id": "bias_battery",
                        "title": "Bias battery",
                        "source": "bias_battery_summary.json",
                        "fields": fields,
                    }
                )

    drift_path = _safe_rel(run_dir, "drift_report.json")
    if drift_path is not None:
        data = _read_json(drift_path)
        if isinstance(data, dict):
            fields = _fields_from_mapping(
                data,
                [
                    "overall_alert_level",
                    "materiality_tier",
                    "recommended_action",
                    "monitor_dataset",
                    "reference_dataset",
                    "run_id",
                ],
            )
            if fields:
                panes.append(
                    {
                        "id": "drift",
                        "title": "Drift",
                        "source": "drift_report.json",
                        "fields": fields,
                    }
                )

    method_path = _safe_rel(run_dir, "translation_methodology_v1.json")
    if method_path is not None:
        data = _read_json(method_path)
        if isinstance(data, dict):
            # Prefer hash / version tokens — no invented metrics
            prefer = [k for k in data.keys() if "hash" in k.lower() or k in {"version", "methodology_id", "id"}]
            fields = _fields_from_mapping(data, prefer[:8]) if prefer else []
            if not fields:
                # First few scalar tokens only
                for k, v in list(data.items())[:6]:
                    if isinstance(v, (str, int, float, bool)) or v is None:
                        fields.append({"key": k, "value": v})
            if fields:
                panes.append(
                    {
                        "id": "methodology",
                        "title": "Methodology",
                        "source": "translation_methodology_v1.json",
                        "fields": fields,
                    }
                )

    audit_path = _safe_rel(run_dir, "audit_chain_verification.json")
    if audit_path is not None:
        data = _read_json(audit_path)
        if isinstance(data, dict):
            fields = _fields_from_mapping(data, ["status", "events"])
            if fields:
                panes.append(
                    {
                        "id": "audit_verify",
                        "title": "Audit verify",
                        "source": "audit_chain_verification.json",
                        "fields": fields,
                    }
                )

    return panes


def wrap_markdown_report(markdown_text: str, *, title: str = "Report") -> str:
    """Minimal HTML shell using DESIGN.md tokens — no metric invention."""
    # Escape is intentional-light: reports are local trusted engine output.
    body = (
        markdown_text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{title}</title>
<style>
  :root {{
    --bg: #0E1114; --panel: #161B20; --elevated: #1E252C; --border: #2A333C;
    --text: #E8EAED; --muted: #9AA3AD; --accent: #D4A574; --selection: #7A93A8;
    --font: "Commit Mono", "CommitMono", ui-monospace, monospace;
    --display: "Cabinet Grotesk", "CabinetGrotesk", system-ui, sans-serif;
  }}
  html, body {{ margin: 0; padding: 0; background: var(--bg); color: var(--text);
    font-family: var(--font); font-size: 14px; line-height: 1.55; }}
  .wrap {{ max-width: 52rem; margin: 0 auto; padding: 16px 18px 32px; }}
  .eyebrow {{ font-size: 11px; color: var(--muted); letter-spacing: 0.04em;
    border-left: 2px solid var(--selection); padding-left: 8px; margin-bottom: 12px; }}
  pre.md {{
    white-space: pre-wrap; word-break: break-word;
    background: var(--elevated); border: 1px solid var(--border);
    border-left: 2px solid var(--accent); border-radius: 4px;
    padding: 14px 16px; margin: 0; font: inherit; color: var(--text);
  }}
  h1.title {{ font-family: var(--display); font-size: 20px; font-weight: 600;
    margin: 0 0 12px; color: var(--text); }}
</style>
</head>
<body>
  <div class="wrap">
    <p class="eyebrow">Review-support report · markdown (engine artifact)</p>
    <h1 class="title">{title}</h1>
    <pre class="md">{body}</pre>
  </div>
</body>
</html>
"""

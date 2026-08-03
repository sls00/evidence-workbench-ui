"""Read-only post-run artifact views (timeline + inspect + compare). No shadow metrics."""

from __future__ import annotations

import difflib
import json
import re
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

GENERATOR_COMPARE_CANDIDATES = (
    "validation.json",
    "panel/validation.json",
)
VALIDATION_COMPARE_CANDIDATES = ("bias_battery_summary.json",)


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


def _resolve_compare_artifact(home: str, run_dir: Path) -> tuple[str | None, Path | None]:
    candidates = GENERATOR_COMPARE_CANDIDATES if home == "generator" else VALIDATION_COMPARE_CANDIDATES
    for rel in candidates:
        path = _safe_rel(run_dir, rel)
        if path is not None:
            return rel, path
    return None, None


def _pretty_json(data: Any) -> list[str]:
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
    return text.splitlines(keepends=True)


def build_compare(
    *,
    home: str,
    left_meta: dict[str, Any],
    right_meta: dict[str, Any],
    left_dir: Path,
    right_dir: Path,
) -> dict[str, Any]:
    """Same-home textual JSON diff of allowlisted compare artifacts."""
    left_status = str(left_meta.get("status") or "")
    right_status = str(right_meta.get("status") or "")
    non_terminal = {"running", "queued", "accepted", "incomplete"}

    if left_status in non_terminal or right_status in non_terminal:
        return {
            "home": home,
            "left": left_meta,
            "right": right_meta,
            "artifact_label": _compare_label(home),
            "empty": True,
            "identical": False,
            "diff_text": "",
            "honesty": "Compare available only for terminal runs with artifacts on disk.",
        }

    left_rel, left_path = _resolve_compare_artifact(home, left_dir)
    right_rel, right_path = _resolve_compare_artifact(home, right_dir)

    left_meta = {**left_meta, "artifact_source": left_rel, "artifact_missing": left_path is None}
    right_meta = {**right_meta, "artifact_source": right_rel, "artifact_missing": right_path is None}

    if left_path is None or right_path is None:
        missing = []
        if left_path is None:
            missing.append("left")
        if right_path is None:
            missing.append("right")
        return {
            "home": home,
            "left": left_meta,
            "right": right_meta,
            "artifact_label": _compare_label(home),
            "empty": True,
            "identical": False,
            "diff_text": "",
            "honesty": f"Compare artifact missing on disk ({', '.join(missing)}).",
        }

    left_data = _read_json(left_path)
    right_data = _read_json(right_path)
    if left_data is None or right_data is None:
        return {
            "home": home,
            "left": left_meta,
            "right": right_meta,
            "artifact_label": _compare_label(home),
            "empty": True,
            "identical": False,
            "diff_text": "",
            "honesty": "Compare artifact unreadable or corrupt JSON.",
        }

    left_lines = _pretty_json(left_data)
    right_lines = _pretty_json(right_data)
    diff_lines = list(
        difflib.unified_diff(
            left_lines,
            right_lines,
            fromfile=f"{left_meta.get('run_id')}/{left_rel}",
            tofile=f"{right_meta.get('run_id')}/{right_rel}",
            lineterm="",
        )
    )
    diff_text = "".join(diff_lines)
    identical = left_data == right_data

    return {
        "home": home,
        "left": left_meta,
        "right": right_meta,
        "artifact_label": _compare_label(home),
        "empty": identical and not diff_text,
        "identical": identical,
        "diff_text": diff_text,
        "honesty": "Artifacts identical — no diff lines." if identical else None,
    }


def _compare_label(home: str) -> str:
    return "validation.json" if home == "generator" else "bias_battery_summary.json"


def _extract_body_html(html: str) -> str:
    lower = html.lower()
    body_start = lower.find("<body")
    if body_start == -1:
        return html.strip()
    open_end = html.find(">", body_start)
    if open_end == -1:
        return html.strip()
    body_end = lower.rfind("</body>")
    if body_end == -1:
        return html[open_end + 1 :].strip()
    return html[open_end + 1 : body_end].strip()


def _report_theme_tokens(theme: str) -> dict[str, str]:
    if theme == "light":
        return {
            "bg": "#F4F5F6",
            "panel": "#FFFFFF",
            "elevated": "#EEF0F2",
            "border": "#D5DAE0",
            "text": "#161B20",
            "muted": "#5C6670",
            "accent": "#9A6B3C",
            "selection": "#4D6578",
        }
    return {
        "bg": "#0E1114",
        "panel": "#161B20",
        "elevated": "#1E252C",
        "border": "#2A333C",
        "text": "#E8EAED",
        "muted": "#9AA3AD",
        "accent": "#D4A574",
        "selection": "#7A93A8",
    }


def _sanitize_embed_fragment(html: str) -> str:
    """Drop engine style hooks that fight the embed shell (download still serves raw file)."""
    html = re.sub(r"<style\b[^>]*>.*?</style>", "", html, flags=re.I | re.S)
    html = re.sub(r'\sstyle="[^"]*"', "", html, flags=re.I)
    html = re.sub(r"\sstyle='[^']*'", "", html, flags=re.I)
    return html.strip()


def wrap_html_report_embed(html_text: str, *, title: str = "Report", theme: str = "dark") -> str:
    """Readable embed shell for engine HTML — DESIGN.md tokens; does not rewrite metrics."""
    tokens = _report_theme_tokens(theme if theme == "light" else "dark")
    fragment = _sanitize_embed_fragment(_extract_body_html(html_text))
    safe_title = (
        title.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta name="color-scheme" content="{theme}"/>
<title>{safe_title}</title>
<style>
  :root {{
    --bg: {tokens["bg"]}; --panel: {tokens["panel"]}; --elevated: {tokens["elevated"]};
    --border: {tokens["border"]}; --text: {tokens["text"]}; --muted: {tokens["muted"]};
    --accent: {tokens["accent"]}; --selection: {tokens["selection"]};
    --font: "Commit Mono", "CommitMono", ui-monospace, monospace;
    --display: "Cabinet Grotesk", "CabinetGrotesk", system-ui, sans-serif;
  }}
  html, body {{ margin: 0; padding: 0; background: var(--bg); color: var(--text);
    font-family: var(--font); font-size: 14px; line-height: 1.55; color-scheme: {theme}; }}
  .wrap {{ max-width: 52rem; margin: 0 auto; padding: 16px 18px 32px; }}
  .eyebrow {{ font-size: 11px; color: var(--muted); letter-spacing: 0.04em;
    border-left: 2px solid var(--selection); padding-left: 8px; margin-bottom: 12px; }}
  .embed-body {{
    background: var(--elevated); border: 1px solid var(--border);
    border-left: 2px solid var(--accent); border-radius: 4px;
    padding: 14px 16px; color: var(--text);
  }}
  /* UA + engine styles often beat :where(); embed shell must win for readability. */
  .embed-body,
  .embed-body h1, .embed-body h2, .embed-body h3, .embed-body h4,
  .embed-body h5, .embed-body h6, .embed-body p, .embed-body li,
  .embed-body td, .embed-body th, .embed-body span, .embed-body div,
  .embed-body pre, .embed-body code, .embed-body label, .embed-body strong {{
    color: var(--text) !important;
    background-color: transparent !important;
  }}
  .embed-body a {{ color: var(--accent) !important; }}
</style>
</head>
<body>
  <div class="wrap">
    <p class="eyebrow">Review-support report · HTML (engine artifact)</p>
    <div class="embed-body">{fragment}</div>
  </div>
</body>
</html>
"""


_OCC_HEADING_RE = re.compile(
    r"(?:§\s*(VII|VI|V|IV|III|II|I)\b|(?<![A-Za-z0-9])(VII|VI|V|IV|III|II|I)\.)",
    re.I,
)


def _escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _inline_md(text: str) -> str:
    """Escape then apply a small set of inline markdown transforms."""
    out = _escape_html(text)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", out)
    out = re.sub(r"(?<!_)_([^_]+)_(?!_)", r"<em>\1</em>", out)
    return out


def _occ_id_from_heading(plain: str) -> str | None:
    m = _OCC_HEADING_RE.search(plain.strip())
    if not m:
        return None
    roman = (m.group(1) or m.group(2) or "").upper()
    return f"occ-{roman.lower()}" if roman else None


def render_markdown_html(markdown_text: str) -> str:
    """Render trusted engine markdown to HTML (headings/lists/paragraphs/code).

    Headings that match OCC §I–§VII / ``I.``…``VII.`` get ``id="occ-i"``…``occ-vii``
    so Validation chrome can scroll the report iframe.
    """
    lines = markdown_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    parts: list[str] = []
    i = 0
    in_code = False
    code_lang = ""
    code_buf: list[str] = []
    list_kind: str | None = None  # "ul" | "ol"

    def close_list() -> None:
        nonlocal list_kind
        if list_kind:
            parts.append(f"</{list_kind}>")
            list_kind = None

    def flush_code() -> None:
        nonlocal in_code, code_lang, code_buf
        body = _escape_html("\n".join(code_buf))
        cls = f' class="language-{_escape_html(code_lang)}"' if code_lang else ""
        parts.append(f"<pre><code{cls}>{body}</code></pre>")
        in_code = False
        code_lang = ""
        code_buf = []

    while i < len(lines):
        line = lines[i]
        if in_code:
            if line.startswith("```"):
                flush_code()
            else:
                code_buf.append(line)
            i += 1
            continue

        fence = re.match(r"^```([\w+-]*)\s*$", line)
        if fence:
            close_list()
            in_code = True
            code_lang = fence.group(1) or ""
            code_buf = []
            i += 1
            continue

        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading:
            close_list()
            level = len(heading.group(1))
            plain = heading.group(2).strip()
            occ_id = _occ_id_from_heading(plain)
            id_attr = f' id="{occ_id}"' if occ_id else ""
            parts.append(f"<h{level}{id_attr}>{_inline_md(plain)}</h{level}>")
            i += 1
            continue

        hr = re.match(r"^(?:-{3,}|\*{3,}|_{3,})\s*$", line)
        if hr:
            close_list()
            parts.append("<hr/>")
            i += 1
            continue

        ul = re.match(r"^[-*+]\s+(.+)$", line)
        if ul:
            if list_kind != "ul":
                close_list()
                parts.append("<ul>")
                list_kind = "ul"
            parts.append(f"<li>{_inline_md(ul.group(1).strip())}</li>")
            i += 1
            continue

        ol = re.match(r"^(\d+)[.)]\s+(.+)$", line)
        if ol:
            if list_kind != "ol":
                close_list()
                parts.append("<ol>")
                list_kind = "ol"
            parts.append(f"<li>{_inline_md(ol.group(2).strip())}</li>")
            i += 1
            continue

        if not line.strip():
            close_list()
            i += 1
            continue

        close_list()
        para = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(
            r"^(#{1,6}\s|```|[-*+]\s|\d+[.)]\s|-{3,}|\*{3,}|_{3,})",
            lines[i],
        ):
            para.append(lines[i])
            i += 1
        parts.append(f"<p>{_inline_md(' '.join(s.strip() for s in para))}</p>")

    if in_code:
        flush_code()
    close_list()
    return "\n".join(parts)


def wrap_markdown_report(markdown_text: str, *, title: str = "Report", theme: str = "dark") -> str:
    """HTML shell with rendered markdown — DESIGN.md tokens; no metric invention."""
    tokens = _report_theme_tokens(theme if theme == "light" else "dark")
    safe_title = _escape_html(title)
    body = render_markdown_html(markdown_text)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta name="color-scheme" content="{theme if theme == "light" else "dark"}"/>
<title>{safe_title}</title>
<style>
  :root {{
    --bg: {tokens["bg"]}; --panel: {tokens["panel"]}; --elevated: {tokens["elevated"]};
    --border: {tokens["border"]}; --text: {tokens["text"]}; --muted: {tokens["muted"]};
    --accent: {tokens["accent"]}; --selection: {tokens["selection"]};
    --font: "Commit Mono", "CommitMono", ui-monospace, monospace;
    --display: "Cabinet Grotesk", "CabinetGrotesk", system-ui, sans-serif;
  }}
  html, body {{ margin: 0; padding: 0; background: var(--bg); color: var(--text);
    font-family: var(--font); font-size: 14px; line-height: 1.55;
    color-scheme: {theme if theme == "light" else "dark"}; }}
  .wrap {{ max-width: 52rem; margin: 0 auto; padding: 16px 18px 32px; }}
  .eyebrow {{ font-size: 11px; color: var(--muted); letter-spacing: 0.04em;
    border-left: 2px solid var(--selection); padding-left: 8px; margin-bottom: 12px; }}
  h1.title {{ font-family: var(--display); font-size: 20px; font-weight: 600;
    margin: 0 0 12px; color: var(--text); }}
  .md-body {{
    background: var(--elevated); border: 1px solid var(--border);
    border-left: 2px solid var(--accent); border-radius: 4px;
    padding: 14px 16px; color: var(--text);
  }}
  .md-body h1, .md-body h2, .md-body h3, .md-body h4, .md-body h5, .md-body h6 {{
    font-family: var(--display); font-weight: 600; line-height: 1.3;
    margin: 1.1em 0 0.45em; color: var(--text); scroll-margin-top: 12px;
  }}
  .md-body h1 {{ font-size: 22px; }}
  .md-body h2 {{ font-size: 18px; }}
  .md-body h3 {{ font-size: 16px; }}
  .md-body p {{ margin: 0 0 0.75em; overflow-wrap: anywhere; }}
  .md-body ul, .md-body ol {{ margin: 0 0 0.75em; padding-left: 1.35em; }}
  .md-body li {{ margin: 0.2em 0; overflow-wrap: anywhere; }}
  .md-body code {{
    font-family: var(--font); font-size: 0.92em;
    background: color-mix(in srgb, var(--bg) 55%, transparent);
    border: 1px solid var(--border); border-radius: 2px; padding: 0 4px;
  }}
  .md-body pre {{
    overflow-x: auto; margin: 0 0 0.85em; padding: 10px 12px;
    background: color-mix(in srgb, var(--bg) 70%, transparent);
    border: 1px solid var(--border); border-radius: 4px;
  }}
  .md-body pre code {{ background: none; border: none; padding: 0; }}
  .md-body hr {{ border: none; border-top: 1px solid var(--border); margin: 1.2em 0; }}
  .md-body a {{ color: var(--accent); }}
</style>
</head>
<body>
  <div class="wrap">
    <p class="eyebrow">Review-support report · markdown (engine artifact)</p>
    <h1 class="title">{safe_title}</h1>
    <div class="md-body">{body}</div>
  </div>
</body>
</html>
"""

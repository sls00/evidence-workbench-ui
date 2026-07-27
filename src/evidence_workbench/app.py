"""
FastAPI orchestrator.

Flow (ASCII):
  POST /api/runs ──202──► {run_id}
  GET  /api/runs/{id} ◄──poll── coarse status
  POST /api/runs/{id}/cancel ──► incomplete + lock free
  GET  /api/runs/{id}/report ──HTML or markdown-wrapped HTML (allowlisted)
  GET  /api/runs/{id}/timeline ──post-run manifest/audit events
  GET  /api/runs/{id}/inspect ──allowlisted metric panes
  GET  /api/runs/compare ──same-home JSON textual diff (Slice C)
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from evidence_workbench.artifacts import wrap_html_report_embed, wrap_markdown_report
from evidence_workbench.orchestrator import BusyError, Orchestrator
from evidence_workbench.preflight import run_preflight
from evidence_workbench.presets import presets_for
from evidence_workbench.settings import Settings, load_settings

Home = Literal["generator", "validation"]


class RunCreate(BaseModel):
    home: Home
    preset_id: str | None = None


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        orch = Orchestrator(settings)
        app.state.settings = settings
        app.state.orch = orch
        yield
        orch.shutdown()

    app = FastAPI(title="Evidence Workbench", version="0.1.0", lifespan=lifespan)

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "fake_runners": settings.fake_runners}

    @app.get("/api/preflight")
    def preflight(home: Home = Query(...)) -> dict[str, Any]:
        result = run_preflight(settings, home)
        return result.to_dict()

    @app.get("/api/presets")
    def presets(home: Home = Query(...)) -> dict[str, Any]:
        return {"home": home, "presets": presets_for(home)}

    @app.post("/api/runs", status_code=202)
    def start_run(body: RunCreate) -> dict[str, Any]:
        orch: Orchestrator = app.state.orch
        # Preflight gate for real runners
        if not settings.fake_runners:
            pf = run_preflight(settings, body.home)
            if not pf.can_run:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "status": "blocked",
                        "error": pf.to_dict().get("error"),
                        "checks": pf.to_dict()["checks"],
                    },
                )
        try:
            active = orch.start_run(body.home, body.preset_id)
        except BusyError as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "status": "busy",
                    "error": {
                        "code": "namespace_busy",
                        "message": f"Namespace {exc.namespace} is busy",
                        "hint": f"Wait for run {exc.run_id} or cancel it",
                    },
                    "busy_run_id": exc.run_id,
                },
            ) from exc
        except KeyError as exc:
            raise HTTPException(
                status_code=400,
                detail={
                    "status": "error",
                    "error": {
                        "code": "unknown_preset",
                        "message": str(exc),
                        "hint": "Use a locked Slice A preset id",
                    },
                },
            ) from exc
        return {"status": "accepted", "run_id": active.run_id, "home": active.home}

    @app.get("/api/runs")
    def list_runs(home: Home = Query(...)) -> dict[str, Any]:
        orch: Orchestrator = app.state.orch
        return orch.list_runs(home)

    @app.get("/api/runs/compare")
    def compare_runs(
        home: Home = Query(...),
        left: str = Query(..., min_length=1),
        right: str = Query(..., min_length=1),
    ) -> dict[str, Any]:
        orch: Orchestrator = app.state.orch
        try:
            return orch.compare(home, left, right)
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "not_found", "message": f"run {exc.args[0]} not found", "hint": ""}},
            ) from exc
        except ValueError as exc:
            code = str(exc)
            messages = {
                "same_run": "Cannot compare a run to itself",
                "cross_home": "Compare is same-home only — pick two runs from one namespace",
            }
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": code,
                        "message": messages.get(code, str(exc)),
                        "hint": "Use two distinct runs from the same home",
                    }
                },
            ) from exc
        except PermissionError as exc:
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "path_traversal", "message": str(exc), "hint": ""}},
            ) from exc

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        orch: Orchestrator = app.state.orch
        try:
            return orch.poll(run_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail={
                    "status": "error",
                    "error": {"code": "not_found", "message": f"run {run_id} not found", "hint": ""},
                },
            ) from exc

    @app.post("/api/runs/{run_id}/cancel")
    def cancel_run(run_id: str) -> dict[str, Any]:
        orch: Orchestrator = app.state.orch
        try:
            return orch.cancel(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": str(run_id), "hint": ""}}) from exc

    @app.get("/api/runs/{run_id}/report", response_model=None)
    def get_report(
        run_id: str,
        download: bool = Query(False),
        theme: Literal["dark", "light"] = Query("dark"),
    ):
        orch: Orchestrator = app.state.orch
        try:
            path = orch.report_path(run_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail={"error": {"code": "no_report", "message": "report missing", "hint": ""}}) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=400, detail={"error": {"code": "path_traversal", "message": str(exc), "hint": ""}}) from exc
        suffix = path.suffix.lower()
        disposition = "attachment" if download else "inline"
        if suffix in {".html", ".htm"}:
            if download:
                return FileResponse(
                    path,
                    media_type="text/html",
                    headers={"Content-Disposition": f'{disposition}; filename="{path.name}"'},
                )
            text = path.read_text(encoding="utf-8")
            html = wrap_html_report_embed(text, title=path.name, theme=theme)
            return HTMLResponse(
                html,
                media_type="text/html",
                headers={"Content-Disposition": f'{disposition}; filename="{path.name}"'},
            )
        if suffix in {".md", ".markdown"}:
            text = path.read_text(encoding="utf-8")
            html = wrap_markdown_report(text, title=path.name)
            out_name = f"{path.stem}.html"
            return HTMLResponse(
                html,
                media_type="text/html",
                headers={"Content-Disposition": f'{disposition}; filename="{out_name}"'},
            )
        return FileResponse(
            path,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'{disposition}; filename="{path.name}"'},
        )

    @app.get("/api/runs/{run_id}/timeline")
    def get_timeline(run_id: str) -> dict[str, Any]:
        orch: Orchestrator = app.state.orch
        try:
            return orch.timeline(run_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "not_found", "message": f"run {run_id} not found", "hint": ""}},
            ) from exc
        except PermissionError as exc:
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "path_traversal", "message": str(exc), "hint": ""}},
            ) from exc

    @app.get("/api/runs/{run_id}/inspect")
    def get_inspect(run_id: str) -> dict[str, Any]:
        orch: Orchestrator = app.state.orch
        try:
            return orch.inspect(run_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "not_found", "message": f"run {run_id} not found", "hint": ""}},
            ) from exc
        except PermissionError as exc:
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "path_traversal", "message": str(exc), "hint": ""}},
            ) from exc

    @app.post("/api/runs/{run_id}/reverify")
    def reverify(run_id: str) -> dict[str, Any]:
        orch: Orchestrator = app.state.orch
        try:
            return orch.reverify(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": str(run_id), "hint": ""}}) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "reverify_unsupported", "message": str(exc), "hint": "Validation home only"}},
            ) from exc

    # Optional: serve built SPA if present (API routes registered above win).
    web_dist = Path(__file__).resolve().parents[2] / "web" / "dist"
    if (web_dist / "index.html").is_file():
        assets = web_dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/")
        def spa_root(request: Request) -> HTMLResponse:
            return HTMLResponse((web_dist / "index.html").read_text(encoding="utf-8"))

        @app.get("/index.html")
        def spa_index() -> HTMLResponse:
            return HTMLResponse((web_dist / "index.html").read_text(encoding="utf-8"))

    return app


# Module-level app for `uvicorn evidence_workbench.app:app`
app = create_app()

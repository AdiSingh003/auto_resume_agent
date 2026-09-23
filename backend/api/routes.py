"""FastAPI REST API routes."""

import os
import json
import uuid
import logging
import asyncio
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse

from backend.models.schemas import GenerateRequest, AgentStatus
from backend.agents.graph import agent_graph, NODE_LABELS, recursion_limit_for
from backend.agents.state import new_state
from backend.tools.resume_parser import parse_resume, validate_upload
from backend.config import settings
from backend.api.job_store import jobs, job_snapshot, trace_event_payload, evaluation_payload
from backend.api.websocket import manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_demo_candidate() -> dict:
    return json.loads((DATA_DIR / "sample_candidate.json").read_text(encoding="utf-8"))


def load_demo_job_description() -> str:
    return (DATA_DIR / "sample_job_description.txt").read_text(encoding="utf-8").strip()


@router.get("/demo")
async def get_demo_data():
    """Bundled demo candidate profile and sample job description."""
    return {
        "job_description": load_demo_job_description(),
        "candidate": load_demo_candidate(),
    }


@router.post("/generate")
async def generate_resume(request: GenerateRequest):
    """Start the resume generation pipeline."""
    job_description = request.job_description.strip()
    if not job_description:
        raise HTTPException(status_code=422, detail="A job description is required")

    candidate_data = load_demo_candidate() if request.use_demo_profile else request.candidate_data
    resume_text = (request.resume_text or "").strip()
    if not candidate_data and not resume_text:
        raise HTTPException(
            status_code=422,
            detail="Provide candidate data, resume text, or use the demo profile",
        )

    job_id = uuid.uuid4().hex[:8]
    state = new_state(
        job_id=job_id,
        job_description=job_description,
        candidate_raw_text=resume_text,
        candidate_data=candidate_data,
        template_style=request.template_style,
    )

    jobs[job_id] = {
        "status": AgentStatus.RUNNING,
        "state": state,
        "active_agent": None,
        "error": None,
    }
    # Keep a reference to the task so it isn't garbage-collected mid-run.
    jobs[job_id]["task"] = asyncio.create_task(_run_pipeline(job_id))

    return {"job_id": job_id, "status": "started"}


async def _run_pipeline(job_id: str):
    """Execute the LangGraph pipeline, mirroring state into the job store and streaming events."""
    job = jobs[job_id]
    state = job["state"]
    config = {"recursion_limit": recursion_limit_for(state["max_revisions"])}

    try:
        async for mode, chunk in agent_graph.astream(
            {**state, "trace": []}, config=config, stream_mode=["updates", "tasks"]
        ):
            if mode == "tasks":
                # Task-start chunks carry "input"; completion chunks carry "result".
                if "input" in chunk:
                    job["active_agent"] = NODE_LABELS.get(chunk["name"], chunk["name"])
                    await manager.broadcast(job_id, {
                        "type": "agent_start",
                        "node": chunk["name"],
                        "agent": job["active_agent"],
                    })
                continue

            for node_name, update in chunk.items():
                if not isinstance(update, dict):
                    continue

                new_events = update.get("trace", [])
                first_seq = len(state["trace"])
                state["trace"].extend(new_events)
                for key, value in update.items():
                    if key != "trace":
                        state[key] = value

                for offset, trace_event in enumerate(new_events):
                    await manager.broadcast(job_id, {
                        "type": "trace",
                        **trace_event_payload(trace_event, first_seq + offset),
                    })

                if update.get("evaluation"):
                    await manager.broadcast(job_id, {
                        "type": "evaluation",
                        **evaluation_payload(update["evaluation"]),
                        "revision_history": state.get("revision_history", []),
                    })

        job["active_agent"] = None
        pdf_path = state.get("pdf_path")
        if state.get("current_agent") == "done" and pdf_path and os.path.exists(pdf_path):
            job["status"] = AgentStatus.COMPLETED
            await manager.broadcast(job_id, {"type": "complete", **job_snapshot(job_id)})
        else:
            job["status"] = AgentStatus.FAILED
            job["error"] = state.get("error") or "Pipeline stopped before producing a resume"
            await manager.broadcast(job_id, {"type": "error", "message": job["error"]})

    except Exception as e:
        logger.exception("Pipeline failed for job %s", job_id)
        job["active_agent"] = None
        job["status"] = AgentStatus.FAILED
        job["error"] = str(e)
        await manager.broadcast(job_id, {"type": "error", "message": str(e)})


def _get_job_state(job_id: str) -> dict:
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]["state"]


def _resume_file(job_id: str, version: Optional[int], extension: str) -> str:
    """Path of the final resume, or of a specific draft version, for a known job."""
    state = _get_job_state(job_id)
    if version is None:
        pdf_path = state.get("pdf_path") or ""
        path = os.path.splitext(pdf_path)[0] + extension if pdf_path else ""
    else:
        path = os.path.join(settings.output_dir, job_id, f"resume_v{version}{extension}")

    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Resume not ready")
    return path


@router.get("/status/{job_id}")
async def get_status(job_id: str):
    """Get the current status of a job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return job_snapshot(job_id)


@router.get("/download/{job_id}/resume")
async def download_resume(
    job_id: str,
    version: Optional[int] = Query(default=None, ge=1),
    inline: bool = False,
):
    """Download the generated resume PDF (final by default, or a specific draft version)."""
    path = _resume_file(job_id, version, ".pdf")
    suffix = f"_v{version}" if version else ""
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"resume_{job_id}{suffix}.pdf",
        content_disposition_type="inline" if inline else "attachment",
    )


@router.get("/download/{job_id}/report")
async def download_report(job_id: str):
    """Download the evidence/change report."""
    state = _get_job_state(job_id)
    report = state.get("evidence_report")

    if not report:
        raise HTTPException(status_code=404, detail="Report not ready")

    # Save report to file and return
    output_dir = os.path.join(settings.output_dir, job_id)
    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, "evidence_report.md")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    return FileResponse(
        report_path,
        media_type="text/markdown",
        filename=f"evidence_report_{job_id}.md",
    )


@router.get("/download/{job_id}/html")
async def download_html(job_id: str, version: Optional[int] = Query(default=None, ge=1)):
    """Resume HTML for in-browser preview (served inline so it renders inside an iframe)."""
    path = _resume_file(job_id, version, ".html")
    return FileResponse(path, media_type="text/html")


@router.post("/upload/resume")
async def upload_resume(file: UploadFile = File(...)):
    """Upload an existing resume file and return its extracted text."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Validate file
    content = await file.read()
    is_valid, msg = validate_upload(file.filename, len(content))
    if not is_valid:
        raise HTTPException(status_code=400, detail=msg)

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Use a safe generated filename
    file_path = upload_dir / f"{uuid.uuid4().hex[:12]}{Path(file.filename).suffix.lower()}"
    file_path.write_bytes(content)

    try:
        text = await asyncio.to_thread(parse_resume, str(file_path))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to parse resume: {e}")
    finally:
        # Only the extracted text is needed; don't keep candidate documents on disk.
        file_path.unlink(missing_ok=True)

    text = text.strip()
    if not text:
        raise HTTPException(
            status_code=422,
            detail="No text could be extracted from this file (is it a scanned image?)",
        )

    return {
        "filename": file.filename,
        "text": text,
        "characters": len(text),
    }

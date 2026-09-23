"""In-memory job registry shared by the REST routes and the WebSocket endpoint."""

import os

# job_id -> {"status": AgentStatus, "state": AgentState, "active_agent": str | None,
#            "error": str | None, "task": asyncio.Task}
jobs: dict[str, dict] = {}


def trace_event_payload(event, seq: int) -> dict:
    """Serialize a trace event; `seq` is its index in the job's trace, used by clients to dedupe."""
    return {
        "seq": seq,
        "agent": event.agent_name,
        "status": event.status.value,
        "message": event.message,
        "timestamp": event.timestamp,
        "details": event.details,
        "duration_ms": event.duration_ms,
    }


def evaluation_payload(evaluation) -> dict | None:
    if not evaluation:
        return None
    return {
        "ats_score": evaluation.ats_score,
        "formatting_score": evaluation.formatting_score,
        "factual_score": evaluation.factual_consistency_score,
        "overall_score": evaluation.overall_score,
        "passed": evaluation.passed,
        "feedback": [
            {
                "category": fb.category,
                "issue": fb.issue,
                "severity": fb.severity,
                "suggestion": fb.suggestion,
            }
            for fb in evaluation.feedback
        ],
    }


def verification_payload(verification) -> dict | None:
    if not verification:
        return None
    return {
        "total_claims": verification.total_claims,
        "verified_claims": verification.verified_claims,
        "fabrication_detected": verification.fabrication_detected,
        "trustworthy": verification.overall_trustworthy,
        "unverified_claims": [
            {"claim": c.claim, "evidence_source": c.evidence_source, "notes": c.notes}
            for c in verification.unverified_claims
        ],
        "removed_claims": verification.removed_claims,
    }


def job_snapshot(job_id: str) -> dict:
    """Full client-facing view of a job: status, complete trace, scores, and artifacts."""
    job = jobs[job_id]
    state = job["state"]
    pdf_path = state.get("pdf_path")
    return {
        "job_id": job_id,
        "status": job["status"].value,
        "active_agent": job.get("active_agent"),
        "error": job.get("error"),
        "revision_count": state.get("revision_count", 0),
        "max_revisions": state.get("max_revisions", 0),
        "trace": [trace_event_payload(t, i) for i, t in enumerate(state.get("trace", []))],
        "evaluation": evaluation_payload(state.get("evaluation")),
        "verification": verification_payload(state.get("verification")),
        "revision_history": state.get("revision_history", []),
        "pdf_ready": bool(pdf_path and os.path.exists(pdf_path)),
        "final_pdf": os.path.basename(pdf_path) if pdf_path else None,
        "report_ready": bool(state.get("evidence_report")),
    }

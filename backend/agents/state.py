"""LangGraph shared state schema for the agent pipeline."""

from __future__ import annotations

import operator
from typing import Annotated, Optional
from typing_extensions import TypedDict

from backend.config import settings
from backend.models.schemas import (
    ParsedJD,
    RoleResearch,
    CandidateProfile,
    EvidenceMap,
    ResumeContent,
    EvaluationResult,
    RevisionPlan,
    VerificationResult,
    AgentTraceEvent,
)


class AgentState(TypedDict):
    """Shared state passed through the LangGraph pipeline.

    Fields annotated with operator.add use append-only reducers,
    so each node can emit new trace events without overwriting history.
    """
    # Inputs
    job_description: str
    candidate_raw_text: str
    candidate_data: Optional[dict]
    template_style: str

    # Agent outputs
    parsed_jd: Optional[ParsedJD]
    role_research: Optional[RoleResearch]
    candidate_profile: Optional[CandidateProfile]
    evidence_map: Optional[EvidenceMap]
    resume_content: Optional[ResumeContent]
    pdf_path: Optional[str]
    evaluation: Optional[EvaluationResult]
    revision_plan: Optional[RevisionPlan]
    verification: Optional[VerificationResult]
    evidence_report: Optional[str]

    # Revision loop bookkeeping
    draft_changes: Optional[dict]   # what the latest draft changed vs. the previous draft
    revision_history: list[dict]    # one entry per evaluated draft: scores, PDF, changes

    # Control flow
    revision_count: int
    max_revisions: int
    current_agent: str
    status: str  # pending, running, completed, failed
    error: Optional[str]

    # Trace — append-only list of events for the UI
    trace: Annotated[list[AgentTraceEvent], operator.add]

    # Job identifier
    job_id: str


def new_state(
    job_id: str,
    job_description: str,
    candidate_raw_text: str = "",
    candidate_data: Optional[dict] = None,
    template_style: str = "modern",
    max_revisions: Optional[int] = None,
) -> AgentState:
    """Build the initial pipeline state for a new job."""
    return {
        "job_description": job_description,
        "candidate_raw_text": candidate_raw_text,
        "candidate_data": candidate_data,
        "template_style": template_style,
        "parsed_jd": None,
        "role_research": None,
        "candidate_profile": None,
        "evidence_map": None,
        "resume_content": None,
        "pdf_path": None,
        "evaluation": None,
        "revision_plan": None,
        "verification": None,
        "evidence_report": None,
        "draft_changes": None,
        "revision_history": [],
        "revision_count": 0,
        "max_revisions": settings.max_revision_cycles if max_revisions is None else max_revisions,
        "current_agent": "parse_jd",
        "status": "running",
        "error": None,
        "trace": [],
        "job_id": job_id,
    }

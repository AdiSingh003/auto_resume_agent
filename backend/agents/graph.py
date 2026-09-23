"""LangGraph workflow definition — the core agentic pipeline with cyclic replanning."""

import logging
from langgraph.graph import StateGraph, END

from backend.agents.state import AgentState
from backend.agents.jd_parser import parse_jd
from backend.agents.role_researcher import research_role
from backend.agents.profile_analyzer import analyze_profile
from backend.agents.evidence_mapper import map_evidence
from backend.agents.resume_drafter import draft_resume
from backend.agents.evaluator import evaluate_resume
from backend.agents.replanner import replan
from backend.agents.verifier import verify_resume
from backend.agents.report_generator import generate_report
from backend.tools.pdf_renderer import render_pdf
from backend.config import settings

logger = logging.getLogger(__name__)

# Human-readable agent name for each graph node (matches AgentTraceEvent.agent_name).
NODE_LABELS = {
    "parse_jd": "JD Parser",
    "research_role": "Role Researcher",
    "analyze_profile": "Profile Analyzer",
    "map_evidence": "Evidence Mapper",
    "draft_resume": "Resume Drafter",
    "render_pdf": "PDF Renderer",
    "evaluate": "Multi-Evaluator",
    "revise": "Replanner",
    "verify": "Final Verifier",
    "report": "Report Generator",
}


def should_revise_or_finalize(state: AgentState) -> str:
    """Conditional edge: decide whether to revise or finalize.

    This is the KEY agentic decision point — the system autonomously
    decides to revise based on evaluation scores, not a fixed chain.
    """
    evaluation = state.get("evaluation")
    revision_count = state.get("revision_count", 0)
    max_revisions = state.get("max_revisions", settings.max_revision_cycles)

    if evaluation is None:
        logger.warning("No evaluation result, proceeding to verification")
        return "verify"

    # Check if we've hit the revision limit
    if revision_count >= max_revisions:
        logger.info(
            "Max revisions (%d) reached. Finalizing with scores: ATS=%d, Format=%d, Factual=%d",
            max_revisions, evaluation.ats_score, evaluation.formatting_score,
            evaluation.factual_consistency_score,
        )
        return "verify"

    # Check if all scores pass thresholds
    if evaluation.passed:
        logger.info(
            "All scores pass thresholds. Finalizing. ATS=%d, Format=%d, Factual=%d",
            evaluation.ats_score, evaluation.formatting_score,
            evaluation.factual_consistency_score,
        )
        return "verify"

    # Check for critical factual issues — always revise these
    critical_factual = any(
        fb.category == "factual" and fb.severity == "critical"
        for fb in evaluation.feedback
    )
    if critical_factual:
        logger.warning("Critical factual issues detected, forcing revision")
        return "revise"

    # Scores below threshold — revise
    logger.info(
        "Scores below threshold (ATS=%d/%d, Format=%d/%d, Factual=%d/%d). Revision #%d",
        evaluation.ats_score, settings.ats_score_threshold,
        evaluation.formatting_score, settings.formatting_score_threshold,
        evaluation.factual_consistency_score, settings.factual_score_threshold,
        revision_count + 1,
    )
    return "revise"


def continue_if_present(key: str, next_node: str):
    """Build a router that ends the run when a prerequisite step produced nothing.

    Without this, a failed JD parse or profile extraction would still flow through
    every downstream agent and "complete" with an empty resume.
    """
    def route(state: AgentState) -> str:
        if state.get(key):
            return next_node
        logger.error("Stopping pipeline: '%s' is missing (%s)", key, state.get("error"))
        return "abort"
    return route


def recursion_limit_for(max_revisions: int) -> int:
    """LangGraph step budget: 4 analysis steps, 3 steps per draft attempt, replans, verify, report."""
    return 4 + 3 * (max_revisions + 1) + max_revisions + 2 + 10


def build_graph() -> StateGraph:
    """Build the LangGraph workflow with the agentic replanning loop.

    Graph structure:
        parse_jd → research_role → analyze_profile → map_evidence
        → draft_resume → render_pdf → evaluate
        → [CONDITIONAL] → revise (→ draft_resume again) OR verify → report → END

    The conditional edge after evaluate is the AUTONOMOUS DECISION POINT.
    """
    workflow = StateGraph(AgentState)

    # Add all nodes
    workflow.add_node("parse_jd", parse_jd)
    workflow.add_node("research_role", research_role)
    workflow.add_node("analyze_profile", analyze_profile)
    workflow.add_node("map_evidence", map_evidence)
    workflow.add_node("draft_resume", draft_resume)
    workflow.add_node("render_pdf", render_pdf)
    workflow.add_node("evaluate", evaluate_resume)
    workflow.add_node("revise", replan)
    workflow.add_node("verify", verify_resume)
    workflow.add_node("report", generate_report)

    # Linear edges, stopping early if a step the rest depends on failed
    workflow.add_conditional_edges(
        "parse_jd", continue_if_present("parsed_jd", "research_role"),
        {"research_role": "research_role", "abort": END},
    )
    workflow.add_edge("research_role", "analyze_profile")
    workflow.add_conditional_edges(
        "analyze_profile", continue_if_present("candidate_profile", "map_evidence"),
        {"map_evidence": "map_evidence", "abort": END},
    )
    workflow.add_edge("map_evidence", "draft_resume")
    workflow.add_edge("draft_resume", "render_pdf")
    workflow.add_conditional_edges(
        "render_pdf", continue_if_present("pdf_path", "evaluate"),
        {"evaluate": "evaluate", "abort": END},
    )

    # THE AGENTIC LOOP: conditional edge after evaluation
    workflow.add_conditional_edges(
        "evaluate",
        should_revise_or_finalize,
        {
            "revise": "revise",    # → replan → draft_resume (loop back)
            "verify": "verify",     # → final verification
        },
    )

    # Revision loop: replan → draft_resume (cycles back through render → evaluate)
    workflow.add_edge("revise", "draft_resume")

    # Final path: verify → report → END
    workflow.add_edge("verify", "report")
    workflow.add_edge("report", END)

    # Entry point
    workflow.set_entry_point("parse_jd")

    return workflow


def compile_graph():
    """Compile the workflow into a runnable graph."""
    workflow = build_graph()
    return workflow.compile()


# Pre-compiled graph instance
agent_graph = compile_graph()

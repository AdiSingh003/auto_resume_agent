"""Agent 8: Replanner — analyzes evaluation feedback and produces specific revision instructions."""

import logging
from datetime import datetime

from backend.agents.state import AgentState
from backend.agents.llm_client import call_llm_json
from backend.agents.common import coerce_model, resume_to_text
from backend.models.schemas import RevisionPlan, AgentTraceEvent, AgentStatus

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a resume revision strategist. Given the current resume draft and its evaluation feedback (ATS, formatting, factual consistency scores and issues), produce a specific revision plan.

CRITICAL RULES:
1. NEVER suggest adding skills, projects, or experience that the candidate doesn't have (see KNOWN GAPS)
2. Focus on: better keyword placement, rephrasing for impact, reordering sections, improving bullet points
3. If factual issues were found, instruct to REMOVE or tone down the problematic claims
4. Prioritize changes that will most improve the weakest score
5. Reference the actual text in the current draft so the instructions are unambiguous

Return a JSON object:
{
    "revision_instructions": [
        {
            "target_section": "summary|skills|experience|projects|education|formatting",
            "action": "rewrite|add|remove|reorder|rephrase",
            "details": "Specific instruction for what to change and how",
            "priority": "high|medium|low"
        }
    ],
    "focus_areas": ["Top 3 areas to focus improvement on"],
    "rationale": "Brief explanation of the revision strategy"
}

Order instructions by priority (high first). Be specific and actionable."""


async def replan(state: AgentState) -> dict:
    """Analyze evaluation feedback and produce a revision plan."""
    start_time = datetime.now()
    trace_events = []
    revision_count = state.get("revision_count", 0) + 1

    trace_events.append(AgentTraceEvent(
        agent_name="Replanner",
        status=AgentStatus.RUNNING,
        message=f"Analyzing evaluation feedback and creating revision plan #{revision_count}...",
    ))

    try:
        evaluation = state.get("evaluation")
        evidence_map = state.get("evidence_map")

        eval_context = ""
        if evaluation:
            eval_context = (
                f"CURRENT SCORES:\n"
                f"  ATS Score: {evaluation.ats_score}/100\n"
                f"  Formatting Score: {evaluation.formatting_score}/100\n"
                f"  Factual Consistency: {evaluation.factual_consistency_score}/100\n\n"
                f"FEEDBACK ({len(evaluation.feedback)} issues):\n"
            )
            for fb in evaluation.feedback:
                eval_context += f"  [{fb.severity.upper()}] [{fb.category}] {fb.issue}\n"
                eval_context += f"    Suggestion: {fb.suggestion}\n"

        gaps_context = ""
        if evidence_map and evidence_map.gaps:
            gaps_context = (
                "KNOWN GAPS (the candidate has no evidence for these — never instruct adding them):\n"
                + "\n".join(f"  - {gap}" for gap in evidence_map.gaps)
            )

        user_prompt = f"""{eval_context}

CURRENT RESUME DRAFT:
{resume_to_text(state.get("resume_content"))}

{gaps_context}

This is revision attempt #{revision_count} of {state.get('max_revisions', 3)}.

Create a focused revision plan to address the most impactful issues.
Return ONLY the JSON object."""

        data = await call_llm_json(SYSTEM_PROMPT, user_prompt)
        revision_plan = coerce_model(RevisionPlan, data)

        duration = int((datetime.now() - start_time).total_seconds() * 1000)

        high_priority = sum(1 for i in revision_plan.revision_instructions if i.priority.lower() == "high")

        trace_events.append(AgentTraceEvent(
            agent_name="Replanner",
            status=AgentStatus.COMPLETED,
            message=f"Revision plan #{revision_count} created: "
                    f"{len(revision_plan.revision_instructions)} changes planned "
                    f"({high_priority} high priority). "
                    f"Focus: {', '.join(revision_plan.focus_areas[:3])}",
            duration_ms=duration,
            details={
                "instruction_count": len(revision_plan.revision_instructions),
                "focus_areas": revision_plan.focus_areas,
                "rationale": revision_plan.rationale[:200],
            },
        ))

        return {
            "revision_plan": revision_plan,
            "revision_count": revision_count,
            "current_agent": "resume_drafter",
            "status": "revising",
            "trace": trace_events,
        }

    except Exception as e:
        logger.error("Replanner failed: %s", e)
        trace_events.append(AgentTraceEvent(
            agent_name="Replanner",
            status=AgentStatus.FAILED,
            message=f"Replanning failed: {str(e)}",
        ))
        return {
            "revision_count": revision_count,
            "current_agent": "resume_drafter",
            "trace": trace_events,
            "error": str(e),
        }

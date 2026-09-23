"""Agent 4: Evidence Mapper — maps JD requirements to genuine candidate evidence."""

import logging
from datetime import datetime

from backend.agents.state import AgentState
from backend.agents.llm_client import call_llm_json
from backend.agents.common import coerce_model, profile_to_text
from backend.models.schemas import EvidenceMap, AgentTraceEvent, AgentStatus

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert career strategist. Your job is to map job description requirements to GENUINE candidate evidence.

CRITICAL RULES:
1. ONLY map to evidence that actually exists in the candidate's profile
2. NEVER fabricate or assume skills/experience not explicitly stated
3. Be honest about gaps — identifying gaps is as important as finding matches
4. Rate each match strength honestly: "strong", "moderate", or "weak"

Return a JSON object:
{
    "matched_requirements": [
        {
            "requirement": "The JD requirement",
            "candidate_evidence": ["Specific evidence from candidate profile that supports this"],
            "strength": "strong|moderate|weak",
            "notes": "How this evidence demonstrates the requirement"
        }
    ],
    "gaps": ["Requirements where the candidate has NO matching evidence"],
    "strongest_fits": ["Top 3-5 areas where the candidate excels for this role"],
    "recommended_focus": ["Key areas the resume should emphasize based on the best matches"]
}

For each requirement, cite SPECIFIC evidence: project names, company names, skill mentions, achievement metrics.
A "strong" match means direct, quantified evidence. "Moderate" means related but not exact. "Weak" means tangential."""


async def map_evidence(state: AgentState) -> dict:
    """Map JD requirements to candidate evidence, identifying strengths and gaps."""
    start_time = datetime.now()
    trace_events = []

    trace_events.append(AgentTraceEvent(
        agent_name="Evidence Mapper",
        status=AgentStatus.RUNNING,
        message="Mapping JD requirements to candidate evidence, identifying gaps and strengths...",
    ))

    try:
        parsed_jd = state.get("parsed_jd")
        profile = state.get("candidate_profile")

        # Build comprehensive context
        jd_section = "JOB REQUIREMENTS:\n"
        if parsed_jd:
            jd_section += f"Title: {parsed_jd.job_title}\n"
            jd_section += f"Required Skills: {', '.join(parsed_jd.required_skills)}\n"
            jd_section += f"Nice-to-Have: {', '.join(parsed_jd.nice_to_have_skills)}\n"
            jd_section += f"Responsibilities: {', '.join(parsed_jd.responsibilities)}\n"
            jd_section += f"Qualifications: {', '.join(parsed_jd.qualifications)}\n"
        else:
            jd_section += state["job_description"][:2000]

        profile_section = "CANDIDATE PROFILE:\n" + profile_to_text(profile)

        user_prompt = f"""{jd_section}

{profile_section}

Map each JD requirement to specific candidate evidence. Be thorough and honest.
Return ONLY the JSON object."""

        data = await call_llm_json(SYSTEM_PROMPT, user_prompt)
        evidence_map = coerce_model(EvidenceMap, data)
        for match in evidence_map.matched_requirements:
            match.strength = match.strength.lower() if match.strength.lower() in ("strong", "moderate", "weak") else "weak"

        duration = int((datetime.now() - start_time).total_seconds() * 1000)

        strong = sum(1 for m in evidence_map.matched_requirements if m.strength == "strong")
        moderate = sum(1 for m in evidence_map.matched_requirements if m.strength == "moderate")
        weak = sum(1 for m in evidence_map.matched_requirements if m.strength == "weak")

        trace_events.append(AgentTraceEvent(
            agent_name="Evidence Mapper",
            status=AgentStatus.COMPLETED,
            message=f"Evidence mapping complete: {strong} strong, {moderate} moderate, "
                    f"{weak} weak matches. {len(evidence_map.gaps)} gaps identified.",
            duration_ms=duration,
            details={
                "strongest_fits": evidence_map.strongest_fits,
                "gaps": evidence_map.gaps[:5],
                "match_summary": {"strong": strong, "moderate": moderate, "weak": weak},
            },
        ))

        return {
            "evidence_map": evidence_map,
            "current_agent": "resume_drafter",
            "trace": trace_events,
        }

    except Exception as e:
        logger.error("Evidence Mapper failed: %s", e)
        trace_events.append(AgentTraceEvent(
            agent_name="Evidence Mapper",
            status=AgentStatus.FAILED,
            message=f"Evidence mapping failed: {str(e)}",
        ))
        return {
            "current_agent": "resume_drafter",
            "trace": trace_events,
            "error": str(e),
        }

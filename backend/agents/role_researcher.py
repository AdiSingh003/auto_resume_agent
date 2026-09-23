"""Agent 2: Role Researcher — researches the target role and company for context."""

import logging
from datetime import datetime

from backend.agents.state import AgentState
from backend.agents.llm_client import call_llm_json
from backend.agents.common import coerce_model
from backend.models.schemas import RoleResearch, AgentTraceEvent, AgentStatus
from backend.tools.web_search import search_role_info

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a career research analyst. Given a parsed job description, provide research context about the role, company, and industry.

Use your knowledge to provide:
1. Industry context and current trends
2. Common tech stacks and tools used in similar roles
3. Company culture indicators (from the JD or general knowledge)
4. What hiring managers typically look for at this level
5. Market insights about this type of role

Return a JSON object:
{
    "industry_context": "Brief paragraph about the industry and trends",
    "common_tech_stack": ["list of commonly used technologies for this role"],
    "company_culture_notes": "Observations about company culture from the JD",
    "role_expectations": ["what hiring managers expect at this seniority level"],
    "market_insights": "Brief paragraph about market demand and positioning"
}

Base your analysis ONLY on the provided JD information, web research results (if any), and general industry knowledge. Be factual and practical."""


async def research_role(state: AgentState) -> dict:
    """Research the target role and company for tailoring context."""
    start_time = datetime.now()
    trace_events = []

    trace_events.append(AgentTraceEvent(
        agent_name="Role Researcher",
        status=AgentStatus.RUNNING,
        message="Researching role requirements, industry trends, and company context...",
    ))

    try:
        parsed_jd = state.get("parsed_jd")

        # Build research context from parsed JD
        if parsed_jd:
            jd_context = (
                f"Job Title: {parsed_jd.job_title}\n"
                f"Company: {parsed_jd.company_name}\n"
                f"Seniority: {parsed_jd.seniority_level.value}\n"
                f"Industry: {parsed_jd.industry}\n"
                f"Required Skills: {', '.join(parsed_jd.required_skills)}\n"
                f"Responsibilities: {', '.join(parsed_jd.responsibilities[:5])}\n"
                f"Company Values: {', '.join(parsed_jd.company_values)}"
            )
        else:
            # Fallback to raw JD
            jd_context = state["job_description"][:2000]

        # Search the web for company/role info; the LLM's own knowledge is the fallback
        search_results = await search_role_info(
            parsed_jd.job_title if parsed_jd else "Software Engineer",
            parsed_jd.company_name if parsed_jd else "",
        )
        source_count = len(search_results.split("\n\n")) if search_results else 0
        search_context = f"\n\nWeb Research Results:\n{search_results}" if search_results else ""

        user_prompt = f"""Research the following role and provide context for resume tailoring.

{jd_context}
{search_context}

Return ONLY the JSON object."""

        data = await call_llm_json(SYSTEM_PROMPT, user_prompt)
        role_research = coerce_model(RoleResearch, data)

        duration = int((datetime.now() - start_time).total_seconds() * 1000)

        sources_note = (
            f"{source_count} web source{'s' if source_count != 1 else ''} consulted"
            if source_count else "web search unavailable, used model knowledge"
        )
        trace_events.append(AgentTraceEvent(
            agent_name="Role Researcher",
            status=AgentStatus.COMPLETED,
            message=f"Research complete ({sources_note}). Identified {len(role_research.common_tech_stack)} relevant "
                    f"technologies and {len(role_research.role_expectations)} key expectations for this role.",
            duration_ms=duration,
            details={
                "web_sources": source_count,
                "tech_stack": role_research.common_tech_stack[:5],
                "expectations": role_research.role_expectations[:3],
            },
        ))

        return {
            "role_research": role_research,
            "current_agent": "profile_analyzer",
            "trace": trace_events,
        }

    except Exception as e:
        logger.error("Role Researcher failed: %s", e)
        trace_events.append(AgentTraceEvent(
            agent_name="Role Researcher",
            status=AgentStatus.FAILED,
            message=f"Research failed: {str(e)}",
        ))
        return {
            "current_agent": "profile_analyzer",
            "trace": trace_events,
            "error": str(e),
        }

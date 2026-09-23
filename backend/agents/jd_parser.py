"""Agent 1: Job Description Parser — extracts structured requirements from raw JD text."""

import logging
from datetime import datetime

from backend.agents.state import AgentState
from backend.agents.llm_client import call_llm_json
from backend.agents.common import coerce_model
from backend.models.schemas import ParsedJD, AgentTraceEvent, AgentStatus

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert job description analyst. Your task is to parse a job description and extract structured information.

You MUST return a valid JSON object with these exact fields:
{
    "job_title": "string",
    "company_name": "string",
    "seniority_level": "intern|junior|mid|senior|lead|principal|executive",
    "required_skills": ["list of required technical and soft skills"],
    "nice_to_have_skills": ["list of preferred/bonus skills"],
    "responsibilities": ["list of key responsibilities"],
    "qualifications": ["list of required qualifications"],
    "company_values": ["list of company values/culture indicators mentioned"],
    "industry": "string - the industry sector",
    "keywords": ["important ATS keywords from the JD"]
}

Extract ONLY what is explicitly stated or clearly implied. Do not invent requirements.
Pay special attention to:
- Technical skills vs soft skills
- Required vs nice-to-have (look for "preferred", "bonus", "nice to have", "plus")
- Years of experience requirements
- Education requirements
- ATS keywords that a resume should include"""


async def parse_jd(state: AgentState) -> dict:
    """Parse the job description into structured requirements."""
    start_time = datetime.now()
    trace_events = []

    trace_events.append(AgentTraceEvent(
        agent_name="JD Parser",
        status=AgentStatus.RUNNING,
        message="Analyzing job description to extract requirements, skills, and keywords...",
    ))

    try:
        jd_text = state["job_description"]

        user_prompt = f"""Parse the following job description and extract all structured information.

JOB DESCRIPTION:
{jd_text}

Return ONLY the JSON object, no other text."""

        data = await call_llm_json(SYSTEM_PROMPT, user_prompt)
        parsed_jd = coerce_model(ParsedJD, data)
        if not (parsed_jd.job_title or parsed_jd.required_skills or parsed_jd.responsibilities):
            raise ValueError("No title, skills, or responsibilities could be extracted from the job description")

        duration = int((datetime.now() - start_time).total_seconds() * 1000)

        trace_events.append(AgentTraceEvent(
            agent_name="JD Parser",
            status=AgentStatus.COMPLETED,
            message=f"Extracted {len(parsed_jd.required_skills)} required skills, "
                    f"{len(parsed_jd.nice_to_have_skills)} nice-to-haves, "
                    f"{len(parsed_jd.keywords)} ATS keywords. "
                    f"Role: {parsed_jd.job_title} at {parsed_jd.company_name} ({parsed_jd.seniority_level.value} level)",
            duration_ms=duration,
            details={
                "required_skills": parsed_jd.required_skills[:5],
                "keywords": parsed_jd.keywords[:5],
            },
        ))

        return {
            "parsed_jd": parsed_jd,
            "current_agent": "role_researcher",
            "trace": trace_events,
        }

    except Exception as e:
        logger.error("JD Parser failed: %s", e)
        trace_events.append(AgentTraceEvent(
            agent_name="JD Parser",
            status=AgentStatus.FAILED,
            message=f"Failed to parse job description: {str(e)}",
        ))
        return {
            "current_agent": "role_researcher",
            "trace": trace_events,
            "error": str(e),
        }

"""Agent 3: Profile Analyzer — extracts structured candidate profile from resume text."""

import json
import logging
from datetime import datetime

from backend.agents.state import AgentState
from backend.agents.llm_client import call_llm_json
from backend.agents.common import coerce_model
from backend.models.schemas import CandidateProfile, AgentTraceEvent, AgentStatus

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert resume parser. Extract ALL information from the candidate's resume into a structured format.

Return a JSON object with these exact fields:
{
    "name": "Full Name",
    "email": "email@example.com",
    "phone": "phone number",
    "location": "City, State/Country",
    "linkedin": "LinkedIn URL if present",
    "github": "GitHub URL if present",
    "portfolio": "Portfolio URL if present",
    "summary": "Professional summary/objective if present",
    "skills": ["list", "of", "all", "skills", "mentioned"],
    "experience": [
        {
            "company": "Company Name",
            "title": "Job Title",
            "start_date": "Start Date",
            "end_date": "End Date or Present",
            "description": "Brief role description",
            "achievements": ["quantified achievements and bullet points"],
            "technologies": ["technologies used in this role"]
        }
    ],
    "projects": [
        {
            "name": "Project Name",
            "description": "What it does",
            "technologies": ["tech used"],
            "url": "project URL if available",
            "highlights": ["key outcomes or features"]
        }
    ],
    "education": [
        {
            "institution": "University Name",
            "degree": "Degree Type",
            "field": "Field of Study",
            "graduation_date": "Date",
            "gpa": "GPA if mentioned",
            "highlights": ["honors, relevant coursework"]
        }
    ],
    "certifications": [
        {
            "name": "Cert Name",
            "issuer": "Issuing Organization",
            "date": "Date",
            "url": "verification URL if available"
        }
    ]
}

Extract ONLY what is explicitly stated. Do NOT infer or fabricate any information.
If a field is not present in the resume, use an empty string or empty list."""


def _has_substance(profile: CandidateProfile) -> bool:
    return bool(profile.skills or profile.experience or profile.projects)


async def analyze_profile(state: AgentState) -> dict:
    """Extract structured candidate profile from resume text or provided data."""
    start_time = datetime.now()
    trace_events = []

    trace_events.append(AgentTraceEvent(
        agent_name="Profile Analyzer",
        status=AgentStatus.RUNNING,
        message="Parsing candidate resume and extracting structured profile data...",
    ))

    try:
        candidate_data = state.get("candidate_data")
        raw_text = (state.get("candidate_raw_text") or "").strip()
        has_structured = isinstance(candidate_data, dict) and bool(candidate_data)

        if has_structured and raw_text:
            source = "structured data + resume text"
            user_prompt = f"""I have both structured candidate data and raw resume text.
Merge them into a single comprehensive profile, preserving ALL information from both sources.

STRUCTURED DATA:
{json.dumps(candidate_data, indent=2, ensure_ascii=False)}

RAW RESUME TEXT:
{raw_text}

Return the merged JSON profile."""
            profile = coerce_model(CandidateProfile, await call_llm_json(SYSTEM_PROMPT, user_prompt))
        elif has_structured:
            source = "structured data"
            profile = coerce_model(CandidateProfile, candidate_data)
            if not _has_substance(profile):
                # JSON in a different shape than our schema — let the LLM map it across.
                source = "structured data (normalized by LLM)"
                user_prompt = f"""Map this candidate JSON onto the profile schema, preserving ALL information.

CANDIDATE JSON:
{json.dumps(candidate_data, indent=2, ensure_ascii=False)}

Return ONLY the JSON object."""
                profile = coerce_model(CandidateProfile, await call_llm_json(SYSTEM_PROMPT, user_prompt))
        elif raw_text:
            source = "resume text"
            user_prompt = f"""Parse the following resume text and extract all information.

RESUME TEXT:
{raw_text}

Return ONLY the JSON object."""
            profile = coerce_model(CandidateProfile, await call_llm_json(SYSTEM_PROMPT, user_prompt))
        else:
            raise ValueError("No candidate data or resume text provided")

        if not _has_substance(profile):
            raise ValueError("Could not extract a usable candidate profile (no skills, experience, or projects found)")

        duration = int((datetime.now() - start_time).total_seconds() * 1000)

        exp_count = len(profile.experience)
        proj_count = len(profile.projects)
        skill_count = len(profile.skills)

        trace_events.append(AgentTraceEvent(
            agent_name="Profile Analyzer",
            status=AgentStatus.COMPLETED,
            message=f"Profile extracted from {source}: {profile.name or 'unnamed candidate'} — "
                    f"{skill_count} skills, {exp_count} experiences, "
                    f"{proj_count} projects, {len(profile.education)} education entries.",
            duration_ms=duration,
            details={
                "name": profile.name,
                "source": source,
                "skills_sample": profile.skills[:8],
                "experience_companies": [e.company for e in profile.experience],
            },
        ))

        return {
            "candidate_profile": profile,
            "current_agent": "evidence_mapper",
            "trace": trace_events,
        }

    except Exception as e:
        logger.error("Profile Analyzer failed: %s", e)
        trace_events.append(AgentTraceEvent(
            agent_name="Profile Analyzer",
            status=AgentStatus.FAILED,
            message=f"Failed to analyze profile: {str(e)}",
        ))
        return {
            "current_agent": "evidence_mapper",
            "trace": trace_events,
            "error": str(e),
        }

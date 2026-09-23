"""Agent 5: Resume Drafter — produces tailored resume content based on evidence mapping."""

import logging
from datetime import datetime

from backend.agents.state import AgentState
from backend.agents.llm_client import call_llm_json
from backend.agents.common import build_resume_content, diff_resumes, profile_to_text, resume_to_text
from backend.models.schemas import AgentTraceEvent, AgentStatus

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert resume writer. Create a tailored, ATS-optimized resume based on the candidate's genuine evidence and the target job requirements.

CRITICAL RULES:
1. NEVER fabricate skills, projects, credentials, employment, or achievements
2. ONLY use information from the candidate's actual profile
3. Rephrase and tailor existing content to match JD keywords — but keep it truthful
4. Use strong action verbs and quantified achievements where available
5. Prioritize the most relevant experience and skills for this specific role
6. Include ATS keywords naturally in context
7. Keep bullet points concise (1-2 lines each)
8. Use reverse chronological order for experience

Return a JSON object:
{
    "header_name": "Full Name",
    "header_contact": "email | phone | location | linkedin | github",
    "professional_summary": "3-4 sentence summary tailored to the role, using the candidate's ACTUAL experience",
    "skills_section": ["Skill 1", "Skill 2", ...],
    "experience_entries": [
        {
            "company": "Company Name",
            "title": "Job Title",
            "dates": "Start - End",
            "location": "City, State",
            "bullets": ["Achievement-focused bullet point with metrics where available"]
        }
    ],
    "project_entries": [
        {
            "name": "Project Name",
            "technologies": "Tech1, Tech2",
            "url": "URL if available",
            "bullets": ["What it does and key outcomes"]
        }
    ],
    "education_entries": [
        {
            "institution": "University",
            "degree": "Degree in Field",
            "date": "Graduation Date",
            "highlights": ["Relevant coursework, honors, GPA if strong"]
        }
    ],
    "certifications": [
        {
            "name": "Certification Name",
            "issuer": "Issuer",
            "date": "Date"
        }
    ],
    "additional_sections": []
}

"skills_section" must be a flat list of individual skills (no category labels).
The skills section should lead with skills matching the JD keywords.
Tailor bullet points to use language from the JD while keeping factual accuracy."""

REVISION_ADDENDUM = """
IMPORTANT: This is a REVISION. You are rewriting the resume based on evaluation feedback.

The current draft, previous evaluation feedback, and revision instructions are provided below.
Address EACH piece of feedback specifically. The resume must improve on the identified weaknesses.

Do NOT change verified facts — only improve phrasing, keyword usage, structure, and emphasis.
"""


async def draft_resume(state: AgentState) -> dict:
    """Draft or revise the tailored resume content."""
    start_time = datetime.now()
    trace_events = []
    revision_count = state.get("revision_count", 0)
    is_revision = revision_count > 0
    previous_resume = state.get("resume_content") if is_revision else None

    trace_events.append(AgentTraceEvent(
        agent_name="Resume Drafter",
        status=AgentStatus.RUNNING,
        message=f"Revising tailored resume (revision #{revision_count})..."
                if is_revision else "Drafting initial tailored resume...",
    ))

    try:
        parsed_jd = state.get("parsed_jd")
        profile = state.get("candidate_profile")
        evidence_map = state.get("evidence_map")
        revision_plan = state.get("revision_plan")

        # Build context
        context_parts = []

        if parsed_jd:
            context_parts.append(
                f"TARGET ROLE: {parsed_jd.job_title} at {parsed_jd.company_name}\n"
                f"Required Skills: {', '.join(parsed_jd.required_skills)}\n"
                f"ATS Keywords: {', '.join(parsed_jd.keywords)}\n"
                f"Seniority: {parsed_jd.seniority_level.value}"
            )

        if profile:
            context_parts.append("CANDIDATE PROFILE (the only permitted source of facts):\n" + profile_to_text(profile))

        if evidence_map:
            evidence_text = "EVIDENCE MAPPING:\n"
            evidence_text += f"Strongest Fits: {', '.join(evidence_map.strongest_fits)}\n"
            evidence_text += f"Focus Areas: {', '.join(evidence_map.recommended_focus)}\n"
            evidence_text += f"Gaps (do NOT fabricate): {', '.join(evidence_map.gaps)}\n"
            context_parts.append(evidence_text)

        # Add revision context if this is a revision
        system = SYSTEM_PROMPT
        if is_revision:
            system += REVISION_ADDENDUM
            if previous_resume:
                context_parts.append(f"CURRENT DRAFT (revise this draft):\n{resume_to_text(previous_resume)}")

            if revision_plan:
                revision_text = f"\nREVISION INSTRUCTIONS (Iteration #{revision_count}):\n"
                revision_text += f"Rationale: {revision_plan.rationale}\n"
                revision_text += f"Focus Areas: {', '.join(revision_plan.focus_areas)}\n"
                for instr in revision_plan.revision_instructions:
                    revision_text += f"  [{instr.priority}] {instr.target_section}: {instr.action} — {instr.details}\n"
                context_parts.append(revision_text)

            # Include previous evaluation
            prev_eval = state.get("evaluation")
            if prev_eval:
                eval_text = f"\nPREVIOUS SCORES: ATS={prev_eval.ats_score}, "
                eval_text += f"Format={prev_eval.formatting_score}, "
                eval_text += f"Factual={prev_eval.factual_consistency_score}\n"
                eval_text += "Feedback:\n"
                for fb in prev_eval.feedback:
                    eval_text += f"  [{fb.severity}] {fb.category}: {fb.issue} → {fb.suggestion}\n"
                context_parts.append(eval_text)

        user_prompt = "\n\n".join(context_parts)
        user_prompt += "\n\nCreate the tailored resume. Return ONLY the JSON object."

        data = await call_llm_json(system, user_prompt, temperature=0.3)
        resume_content = build_resume_content(data)

        # Fallback for LLMs that occasionally drop top-level fields
        if not resume_content.header_name and profile:
            resume_content.header_name = profile.name
        if not resume_content.header_contact and profile:
            contact = [profile.email, profile.phone, profile.location, profile.linkedin, profile.github]
            resume_content.header_contact = " | ".join(c for c in contact if c)
        if not resume_content.professional_summary and profile:
            resume_content.professional_summary = profile.summary

        if not (resume_content.experience_entries or resume_content.project_entries or resume_content.skills_section):
            raise ValueError("The drafted resume contained no experience, projects, or skills")

        changes = diff_resumes(previous_resume, resume_content)
        duration = int((datetime.now() - start_time).total_seconds() * 1000)

        message = (
            f"Resume {'revised' if is_revision else 'drafted'}: "
            f"{len(resume_content.experience_entries)} experiences, "
            f"{len(resume_content.project_entries)} projects, "
            f"{len(resume_content.skills_section)} skills."
        )
        if is_revision:
            message += (
                f" Changes vs. previous draft: {len(changes['added'])} bullets rewritten/added, "
                f"{len(changes['removed'])} replaced/removed"
                f"{', summary rewritten' if changes['summary_changed'] else ''}."
            )

        trace_events.append(AgentTraceEvent(
            agent_name="Resume Drafter",
            status=AgentStatus.COMPLETED,
            message=message,
            duration_ms=duration,
            details={
                "skills_count": len(resume_content.skills_section),
                "experience_count": len(resume_content.experience_entries),
                "is_revision": is_revision,
                "revision_number": revision_count,
                "bullets_added": len(changes["added"]),
                "bullets_removed": len(changes["removed"]),
            },
        ))

        return {
            "resume_content": resume_content,
            "draft_changes": changes,
            "current_agent": "pdf_renderer",
            "trace": trace_events,
        }

    except Exception as e:
        logger.error("Resume Drafter failed: %s", e)
        trace_events.append(AgentTraceEvent(
            agent_name="Resume Drafter",
            status=AgentStatus.FAILED,
            message=f"Drafting failed: {str(e)}",
        ))
        return {
            "current_agent": "pdf_renderer",
            "trace": trace_events,
            "error": str(e),
        }

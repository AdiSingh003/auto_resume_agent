"""Agent 7: Multi-Evaluator — scores the resume on ATS relevance, formatting, and factual consistency."""

import os
import logging
from datetime import datetime

from backend.agents.state import AgentState
from backend.agents.llm_client import call_llm_json
from backend.agents.common import SEVERITIES, candidate_source_text, coerce_model, resume_to_text, to_score
from backend.models.schemas import EvaluationResult, EvaluationFeedback, AgentTraceEvent, AgentStatus
from backend.config import settings

logger = logging.getLogger(__name__)

ATS_EVALUATOR_PROMPT = """You are an ATS (Applicant Tracking System) simulator. Score this resume against the job description.

Evaluate:
1. Keyword match rate — how many JD keywords appear in the resume?
2. Skills alignment — do listed skills match required skills?
3. Experience relevance — do job titles and achievements align with the role?
4. Quantified achievements — are metrics and numbers included?
5. Format compatibility — is the rendered PDF machine-readable (extractable text)?

Return a JSON object:
{
    "ats_score": 0-100,
    "feedback": [
        {
            "category": "ats",
            "issue": "Specific issue found",
            "severity": "low|medium|high|critical",
            "suggestion": "How to fix it"
        }
    ]
}"""

FORMATTING_EVALUATOR_PROMPT = """You are a resume formatting expert. Evaluate the resume structure and presentation.

Evaluate:
1. Section organization and logical flow
2. Bullet point quality (action verbs, conciseness)
3. Consistency in formatting (dates, capitalization)
4. Length appropriateness for the candidate's experience level (see the rendered PDF page count; one page is ideal under ~10 years of experience)
5. Professional summary quality
6. White space and readability

Return a JSON object:
{
    "formatting_score": 0-100,
    "feedback": [
        {
            "category": "formatting",
            "issue": "Specific issue found",
            "severity": "low|medium|high|critical",
            "suggestion": "How to fix it"
        }
    ]
}"""

FACTUAL_EVALUATOR_PROMPT = """You are a factual consistency checker. Compare the tailored resume against the original candidate profile.

CRITICAL: Identify ANY claim in the resume that is NOT supported by the original candidate data.
This includes:
- Skills not mentioned in the original profile
- Projects or achievements that were embellished beyond the source
- Job titles or company names that were changed
- Metrics or numbers that were added without source evidence
- Education or certifications not in the original profile

Reasonable rephrasing and standard umbrella terms for listed technologies are NOT fabrications.

Return a JSON object:
{
    "factual_score": 0-100,
    "feedback": [
        {
            "category": "factual",
            "issue": "Specific factual concern",
            "severity": "low|medium|high|critical",
            "suggestion": "How to address it"
        }
    ]
}

A score of 100 means every claim is traceable to the original data.
Any fabricated content should result in a "critical" severity finding."""


def inspect_pdf(pdf_path: str | None) -> tuple[int, int]:
    """Return (page_count, extractable_text_chars) for the rendered PDF, or (0, 0) if unavailable."""
    if not pdf_path or not os.path.exists(pdf_path):
        return 0, 0
    try:
        import pymupdf

        with pymupdf.open(pdf_path) as doc:
            return doc.page_count, sum(len(page.get_text()) for page in doc)
    except Exception as e:
        logger.warning("Could not inspect rendered PDF %s: %s", pdf_path, e)
        return 0, 0


def _feedback_items(items, category: str) -> list[EvaluationFeedback]:
    feedback = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        fb = coerce_model(EvaluationFeedback, item)
        fb.category = (fb.category or category).lower()
        fb.severity = fb.severity.lower() if fb.severity.lower() in SEVERITIES else "medium"
        if fb.issue:
            feedback.append(fb)
    return feedback


async def _run_sub_evaluation(label: str, category: str, score_key: str, system_prompt: str, user_prompt: str):
    """Run one sub-evaluator. A failure yields a neutral score plus a note instead of failing the node."""
    try:
        data = await call_llm_json(system_prompt, user_prompt)
        return to_score(data.get(score_key)), _feedback_items(data.get("feedback"), category)
    except Exception as e:
        logger.warning("%s evaluation failed: %s", label, e)
        return 50, [EvaluationFeedback(
            category=category,
            issue=f"{label} evaluator unavailable ({e}); score defaulted to 50.",
            severity="low",
            suggestion="Re-run the pipeline to get a real score.",
        )]


async def evaluate_resume(state: AgentState) -> dict:
    """Run three sub-evaluations: ATS, formatting, and factual consistency."""
    start_time = datetime.now()
    trace_events = []

    trace_events.append(AgentTraceEvent(
        agent_name="Multi-Evaluator",
        status=AgentStatus.RUNNING,
        message="Running ATS relevance, formatting quality, and factual consistency evaluations...",
    ))

    parsed_jd = state.get("parsed_jd")
    resume_text = resume_to_text(state.get("resume_content"))

    if parsed_jd:
        jd_text = (
            f"Job: {parsed_jd.job_title}\n"
            f"Required Skills: {', '.join(parsed_jd.required_skills)}\n"
            f"Keywords: {', '.join(parsed_jd.keywords)}\n"
            f"Responsibilities: {', '.join(parsed_jd.responsibilities)}"
        )
    else:
        jd_text = state["job_description"][:3000]

    pdf_path = state.get("pdf_path")
    page_count, text_chars = inspect_pdf(pdf_path)
    pdf_facts = (
        f"RENDERED PDF: {page_count} page(s), {text_chars} characters of machine-extractable text."
        if page_count else "RENDERED PDF: not available."
    )

    ats_score, ats_feedback = await _run_sub_evaluation(
        "ATS", "ats", "ats_score", ATS_EVALUATOR_PROMPT,
        f"RESUME:\n{resume_text}\n\n{pdf_facts}\n\nJOB DESCRIPTION:\n{jd_text}\n\n"
        "Evaluate ATS compatibility. Return ONLY the JSON.",
    )
    formatting_score, formatting_feedback = await _run_sub_evaluation(
        "Formatting", "formatting", "formatting_score", FORMATTING_EVALUATOR_PROMPT,
        f"RESUME:\n{resume_text}\n\n{pdf_facts}\n\nEvaluate formatting quality. Return ONLY the JSON.",
    )
    factual_score, factual_feedback = await _run_sub_evaluation(
        "Factual", "factual", "factual_score", FACTUAL_EVALUATOR_PROMPT,
        f"TAILORED RESUME:\n{resume_text}\n\nORIGINAL CANDIDATE DATA:\n{candidate_source_text(state)}\n\n"
        "Check factual consistency. Return ONLY the JSON.",
    )

    all_feedback = ats_feedback + formatting_feedback + factual_feedback
    overall_score = (ats_score + formatting_score + factual_score) // 3

    # Determine if passed
    passed = (
        ats_score >= settings.ats_score_threshold
        and formatting_score >= settings.formatting_score_threshold
        and factual_score >= settings.factual_score_threshold
    )

    evaluation = EvaluationResult(
        ats_score=ats_score,
        formatting_score=formatting_score,
        factual_consistency_score=factual_score,
        overall_score=overall_score,
        feedback=all_feedback,
        passed=passed,
    )

    duration = int((datetime.now() - start_time).total_seconds() * 1000)

    critical_issues = sum(1 for fb in all_feedback if fb.severity == "critical")
    high_issues = sum(1 for fb in all_feedback if fb.severity == "high")
    version = state.get("revision_count", 0) + 1

    history_entry = {
        "version": version,
        "ats_score": ats_score,
        "formatting_score": formatting_score,
        "factual_score": factual_score,
        "overall_score": overall_score,
        "passed": passed,
        "pages": page_count,
        "pdf_file": os.path.basename(pdf_path) if pdf_path else None,
        "issue_count": len(all_feedback),
        "critical_issues": critical_issues,
        "changes": state.get("draft_changes") or {},
    }

    trace_events.append(AgentTraceEvent(
        agent_name="Multi-Evaluator",
        status=AgentStatus.COMPLETED,
        message=f"Draft v{version} — ATS: {ats_score}/100, Format: {formatting_score}/100, "
                f"Factual: {factual_score}/100 (Overall: {overall_score}/100). "
                f"{'PASSED ✓' if passed else 'NEEDS REVISION ✗'} | "
                f"{critical_issues} critical, {high_issues} high issues.",
        duration_ms=duration,
        details={
            "version": version,
            "ats_score": ats_score,
            "formatting_score": formatting_score,
            "factual_score": factual_score,
            "overall_score": overall_score,
            "passed": passed,
            "pages": page_count,
            "issue_count": len(all_feedback),
        },
    ))

    return {
        "evaluation": evaluation,
        "revision_history": [*state.get("revision_history", []), history_entry],
        "current_agent": "decision",
        "trace": trace_events,
    }

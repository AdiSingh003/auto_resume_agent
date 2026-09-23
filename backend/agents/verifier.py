"""Agent 9: Final Verifier — cross-checks every resume claim against original candidate data.

Guardrail: claims the verifier cannot trace to the candidate's data are removed from the
resume (not just flagged), and the final PDF is re-rendered without them.
"""

import asyncio
import logging
from datetime import datetime

from backend.agents.state import AgentState
from backend.agents.llm_client import call_llm_json
from backend.agents.common import (
    as_bool,
    candidate_source_text,
    coerce_model,
    remove_claims,
    resume_to_text,
    supported_by_source,
    to_int,
)
from backend.models.schemas import VerificationResult, ClaimVerification, AgentTraceEvent, AgentStatus
from backend.tools.pdf_renderer import render_resume_files

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a meticulous factual verification agent. Your job is to compare the FINAL resume against the ORIGINAL candidate data and verify every claim.

For EACH significant claim in the resume (skills, job titles, companies, achievements, projects, education, certifications, metrics), verify:
1. Is this claim present in the original candidate data?
2. Has it been embellished beyond what the source supports?
3. Were any details fabricated or assumed?

Return a JSON object:
{
    "total_claims": <number of significant claims checked>,
    "verified_claims": <number that are fully supported by original data>,
    "unverified_claims": [
        {
            "claim": "The unsupported text copied EXACTLY from the resume: the whole bullet point, the exact skill name, or the exact summary sentence",
            "verified": false,
            "evidence_source": "What the original data actually says (or 'NOT FOUND')",
            "notes": "Why this is flagged"
        }
    ],
    "fabrication_detected": true/false,
    "overall_trustworthy": true/false
}

Be STRICT, but fair. If a bullet point rephrases original content in a reasonable way, that's fine (verified).
A skill or technology is verified if it appears ANYWHERE in the original data — the skills list, experience
descriptions, achievements, technologies, or projects — not only in the skills list.
Standard umbrella terms for listed technologies (e.g. "AWS" for "AWS (EC2, S3, Lambda)") are verified.
Only list a claim in "unverified_claims" if it adds skills, metrics, achievements, credentials, or
responsibilities the original data does not support — every listed claim will be REMOVED from the resume.
"fabrication_detected" should be true ONLY if there are clear fabrications (not just rephrasing)."""


async def verify_resume(state: AgentState) -> dict:
    """Final verification: cross-check resume claims against original data and strip unsupported ones."""
    start_time = datetime.now()
    trace_events = []

    trace_events.append(AgentTraceEvent(
        agent_name="Final Verifier",
        status=AgentStatus.RUNNING,
        message="Cross-checking every resume claim against original candidate data for factual accuracy...",
    ))

    try:
        resume_content = state.get("resume_content")
        source_text = candidate_source_text(state)

        user_prompt = f"""FINAL RESUME TO VERIFY:
{resume_to_text(resume_content)}

ORIGINAL CANDIDATE DATA (source of truth):
{source_text}

Verify every claim. Return ONLY the JSON object."""

        data = await call_llm_json(SYSTEM_PROMPT, user_prompt)

        claims = data.get("unverified_claims")
        flagged = [
            claim
            for claim in (coerce_model(ClaimVerification, item) for item in (claims if isinstance(claims, list) else []) if isinstance(item, dict))
            if claim.claim and not claim.verified
        ]
        # The LLM sometimes flags skills that do appear in the source (e.g. only inside an achievement).
        # Anything that literally appears in the candidate's own data is never removed.
        unverified = [claim for claim in flagged if not supported_by_source(claim.claim, source_text)]
        overruled = len(flagged) - len(unverified)

        # Remove unsupported claims and re-render, so the delivered PDF contains only verified content.
        removed: list[str] = []
        final_update: dict = {}
        if unverified and resume_content:
            cleaned = resume_content.model_copy(deep=True)
            removed = remove_claims(cleaned, [c.claim for c in unverified])
            if removed:
                try:
                    rendered = await asyncio.to_thread(
                        render_resume_files,
                        cleaned,
                        state.get("template_style", "modern"),
                        state.get("job_id", "default"),
                        "resume_final",
                    )
                    final_update = {"resume_content": cleaned, "pdf_path": rendered["pdf_path"]}
                except Exception as e:
                    logger.error("Re-rendering after claim removal failed; keeping previous PDF: %s", e)
                    removed = []

        verification = VerificationResult(
            total_claims=to_int(data.get("total_claims")),
            verified_claims=to_int(data.get("verified_claims")),
            unverified_claims=unverified,
            fabrication_detected=as_bool(data.get("fabrication_detected")) and bool(unverified),
            overall_trustworthy=as_bool(data.get("overall_trustworthy"), default=True) or not unverified,
            removed_claims=removed,
        )

        duration = int((datetime.now() - start_time).total_seconds() * 1000)

        trust_status = "✓ TRUSTWORTHY" if verification.overall_trustworthy else "⚠ CONCERNS FOUND"
        fab_status = " | ⛔ FABRICATION DETECTED" if verification.fabrication_detected else ""
        message = (
            f"Verification complete: {verification.verified_claims}/{verification.total_claims} "
            f"claims verified. {trust_status}{fab_status}"
        )
        if removed:
            message += f" Removed {len(removed)} unsupported item(s) and re-rendered resume_final.pdf."
        elif unverified:
            message += f" {len(unverified)} flagged claim(s) did not match resume text, so nothing was removed."
        if overruled:
            message += f" {overruled} flag(s) overruled because the text appears in the candidate's own data."

        trace_events.append(AgentTraceEvent(
            agent_name="Final Verifier",
            status=AgentStatus.COMPLETED,
            message=message,
            duration_ms=duration,
            details={
                "total_claims": verification.total_claims,
                "verified_claims": verification.verified_claims,
                "unverified_count": len(verification.unverified_claims),
                "overruled_flags": overruled,
                "removed_claims": removed[:10],
                "fabrication_detected": verification.fabrication_detected,
                "trustworthy": verification.overall_trustworthy,
            },
        ))

        return {
            "verification": verification,
            **final_update,
            "current_agent": "report_generator",
            "trace": trace_events,
        }

    except Exception as e:
        logger.error("Final Verifier failed: %s", e)
        trace_events.append(AgentTraceEvent(
            agent_name="Final Verifier",
            status=AgentStatus.FAILED,
            message=f"Verification failed: {str(e)}",
        ))
        return {
            "current_agent": "report_generator",
            "trace": trace_events,
            "error": str(e),
        }

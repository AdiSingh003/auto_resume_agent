"""Agent 10: Report Generator — produces the evidence/change report explaining all edits."""

import os
import re
import logging
from datetime import datetime

from backend.agents.state import AgentState
from backend.agents.llm_client import call_llm
from backend.models.schemas import AgentTraceEvent, AgentStatus
from backend.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a documentation specialist. Generate a comprehensive evidence and change report for the resume tailoring process.

The report should explain:
1. What the target role requires
2. What evidence from the candidate was used
3. Key tailoring decisions made and WHY
4. How the resume was optimized for ATS
5. What gaps exist (honestly)
6. Evaluation scores and what they mean
7. Verification results — any concerns, and exactly which unsupported claims were removed
8. Revision history — how scores changed across drafts and what each revision changed

Write in clear, professional markdown format. Start each of these topics with a "## " heading.
Use bullet points and tables. Do not wrap the report in a code fence, and do not use HTML tags (such as <br>).
Be transparent about both strengths and limitations of the tailored resume.

The report should be useful for the candidate to understand exactly what was changed and why."""


def _strip_outer_fence(text: str) -> str:
    stripped = text.strip()
    match = re.fullmatch(r"```(?:markdown|md)?\s*\n(.*)\n```", stripped, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else stripped


async def generate_report(state: AgentState) -> dict:
    """Generate the final evidence/change report."""
    start_time = datetime.now()
    trace_events = []

    trace_events.append(AgentTraceEvent(
        agent_name="Report Generator",
        status=AgentStatus.RUNNING,
        message="Generating comprehensive evidence and change report...",
    ))

    try:
        parsed_jd = state.get("parsed_jd")
        candidate_profile = state.get("candidate_profile")
        evidence_map = state.get("evidence_map")
        evaluation = state.get("evaluation")
        verification = state.get("verification")
        revision_plan = state.get("revision_plan")
        revision_count = state.get("revision_count", 0)

        # Build context
        context_parts = []

        if parsed_jd:
            context_parts.append(
                f"TARGET ROLE: {parsed_jd.job_title} at {parsed_jd.company_name}\n"
                f"Seniority: {parsed_jd.seniority_level.value}\n"
                f"Required Skills: {', '.join(parsed_jd.required_skills)}\n"
                f"Keywords: {', '.join(parsed_jd.keywords)}"
            )

        if candidate_profile:
            context_parts.append(
                f"CANDIDATE: {candidate_profile.name}\n"
                f"Skills: {', '.join(candidate_profile.skills[:15])}\n"
                f"Experience Count: {len(candidate_profile.experience)}\n"
                f"Projects Count: {len(candidate_profile.projects)}"
            )

        if evidence_map:
            strong = sum(1 for m in evidence_map.matched_requirements if m.strength == "strong")
            moderate = sum(1 for m in evidence_map.matched_requirements if m.strength == "moderate")
            weak = sum(1 for m in evidence_map.matched_requirements if m.strength == "weak")
            matches = "\n".join(
                f"  - {m.requirement} [{m.strength}]: {'; '.join(m.candidate_evidence[:2])}"
                for m in evidence_map.matched_requirements
            )
            context_parts.append(
                f"EVIDENCE MAPPING:\n"
                f"Strong matches: {strong}, Moderate: {moderate}, Weak: {weak}\n"
                f"{matches}\n"
                f"Gaps: {', '.join(evidence_map.gaps)}\n"
                f"Strongest fits: {', '.join(evidence_map.strongest_fits)}"
            )

        if evaluation:
            context_parts.append(
                f"FINAL EVALUATION SCORES:\n"
                f"ATS: {evaluation.ats_score}/100\n"
                f"Formatting: {evaluation.formatting_score}/100\n"
                f"Factual Consistency: {evaluation.factual_consistency_score}/100\n"
                f"Overall: {evaluation.overall_score}/100\n"
                f"Issues found: {len(evaluation.feedback)}\n"
                f"Key feedback: {'; '.join(fb.issue for fb in evaluation.feedback[:5])}"
            )

        history = state.get("revision_history", [])
        if history:
            lines = ["REVISION HISTORY (one line per draft):"]
            for entry in history:
                changes = entry.get("changes") or {}
                lines.append(
                    f"  Draft v{entry['version']}: ATS {entry['ats_score']}, Format {entry['formatting_score']}, "
                    f"Factual {entry['factual_score']}, Overall {entry['overall_score']} "
                    f"({'passed' if entry['passed'] else 'below threshold'}); "
                    f"{len(changes.get('added', []))} bullets added, {len(changes.get('removed', []))} removed, "
                    f"skills added: {', '.join(changes.get('skills_added', [])) or 'none'}"
                )
            if revision_plan:
                lines.append(f"Last revision rationale: {revision_plan.rationale}")
            context_parts.append("\n".join(lines))
        context_parts.append(f"TOTAL REVISIONS PERFORMED: {revision_count}")

        if verification:
            unverified = "\n".join(
                f"  - \"{c.claim}\" — source says: {c.evidence_source}; {c.notes}"
                for c in verification.unverified_claims
            )
            removed = "\n".join(f"  - {item}" for item in verification.removed_claims)
            context_parts.append(
                f"VERIFICATION:\n"
                f"Claims verified: {verification.verified_claims}/{verification.total_claims}\n"
                f"Fabrication detected: {verification.fabrication_detected}\n"
                f"Overall trustworthy: {verification.overall_trustworthy}\n"
                f"Unverified claims:\n{unverified or '  none'}\n"
                f"Removed from final resume:\n{removed or '  none'}"
            )

        # Build trace summary
        trace_summary = "AGENT TRACE SUMMARY:\n"
        for event in state.get("trace", []):
            if event.status != AgentStatus.RUNNING:
                trace_summary += f"  [{event.status.value}] {event.agent_name}: {event.message[:160]}\n"
        context_parts.append(trace_summary)

        user_prompt = (
            "\n\n".join(context_parts)
            + "\n\nGenerate the comprehensive evidence and change report in markdown format."
        )

        report = _strip_outer_fence(await call_llm(SYSTEM_PROMPT, user_prompt, temperature=0.3))

        output_dir = os.path.join(settings.output_dir, state.get("job_id", "default"))
        os.makedirs(output_dir, exist_ok=True)
        with open(os.path.join(output_dir, "evidence_report.md"), "w", encoding="utf-8") as f:
            f.write(report)

        duration = int((datetime.now() - start_time).total_seconds() * 1000)

        trace_events.append(AgentTraceEvent(
            agent_name="Report Generator",
            status=AgentStatus.COMPLETED,
            message=f"Evidence report generated ({len(report)} chars). "
                    f"Pipeline complete after {revision_count} revision(s).",
            duration_ms=duration,
        ))

        return {
            "evidence_report": report,
            "current_agent": "done",
            "status": "completed",
            "trace": trace_events,
        }

    except Exception as e:
        logger.error("Report Generator failed: %s", e)
        trace_events.append(AgentTraceEvent(
            agent_name="Report Generator",
            status=AgentStatus.FAILED,
            message=f"Report generation failed: {str(e)}",
        ))
        return {
            "current_agent": "done",
            "status": "completed",
            "trace": trace_events,
            "error": str(e),
        }

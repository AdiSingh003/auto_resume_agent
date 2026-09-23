"""Runs the full LangGraph pipeline with stubbed LLM calls: exercises the revision loop,
PDF rendering, verification-driven claim removal, and report generation without network access."""

import asyncio
import os

import pymupdf

from backend.agents import (
    evaluator,
    evidence_mapper,
    jd_parser,
    replanner,
    report_generator,
    resume_drafter,
    role_researcher,
    verifier,
)
from backend.agents.graph import agent_graph, recursion_limit_for
from backend.agents.state import new_state
from backend.api.routes import load_demo_candidate, load_demo_job_description
from backend.config import settings
from backend.models.schemas import AgentStatus

FABRICATED_BULLET = "Increased platform revenue by $5M through a new recommendation engine."

DRAFT = {
    "header_name": "Alex Chen",
    "header_contact": "alex.chen@example.com | San Francisco, CA",
    "professional_summary": "Senior backend engineer with 5 years of Python and Kafka experience.",
    "skills_section": ["Python", "FastAPI", "Kafka", "Docker", "AWS"],
    "experience_entries": [{
        "company": "TechFlow Inc.",
        "title": "Senior Software Engineer",
        "dates": "2022 - Present",
        "bullets": [
            "Architected a real-time data pipeline using Python and Kafka, reducing data latency by 40%.",
            FABRICATED_BULLET,
        ],
    }],
    "education_entries": [{"institution": "UC Berkeley", "degree": "B.S. Computer Science", "date": "2019"}],
}


def _stub_llm(monkeypatch):
    calls = {"ats": 0}

    async def fake_call_llm_json(system, user, temperature=0.2):
        if "job description analyst" in system:
            return {"job_title": "Senior Software Engineer", "company_name": "TechNova Solutions",
                    "seniority_level": "Senior", "required_skills": ["Python", "Kafka"], "keywords": ["Python"]}
        if "career research analyst" in system:
            return {"common_tech_stack": ["Python", "Kafka"], "role_expectations": ["Lead backend work"]}
        if "career strategist" in system:
            return {"matched_requirements": [{"requirement": "Python", "candidate_evidence": ["TechFlow"],
                                              "strength": "Strong"}], "gaps": ["Rust"]}
        if "expert resume writer" in system:
            return DRAFT
        if system.startswith("You are an ATS"):
            calls["ats"] += 1
            return {"ats_score": 60 if calls["ats"] == 1 else "92/100",
                    "feedback": [{"category": "ATS", "issue": "Missing keywords", "severity": "High"}]}
        if "formatting expert" in system:
            return {"formatting_score": 90, "feedback": []}
        if "factual consistency checker" in system:
            return {"factual_score": 95.0, "feedback": []}
        if "revision strategist" in system:
            assert "CURRENT RESUME DRAFT" in user and "Rust" in user
            return {"revision_instructions": [{"target_section": "skills", "action": "reorder",
                                               "details": "Lead with Kafka", "priority": "high"}],
                    "focus_areas": ["keywords"], "rationale": "Improve ATS match"}
        if "factual verification agent" in system:
            return {"total_claims": 10, "verified_claims": "9", "fabrication_detected": "true",
                    "overall_trustworthy": False,
                    "unverified_claims": [{"claim": FABRICATED_BULLET, "verified": False,
                                           "evidence_source": "NOT FOUND", "notes": "No revenue metric in source"},
                                          # False positive: Kafka appears in the candidate's achievements.
                                          {"claim": "Kafka", "verified": False, "evidence_source": "NOT FOUND"}]}
        raise AssertionError(f"Unexpected prompt: {system[:80]}")

    async def fake_call_llm(system, user, temperature=0.2):
        return "```markdown\n## Summary\nReport body\n```"

    async def fake_search(job_title, company_name=""):
        return "[Result] Backend roles need Python.\n\n[Result] Kafka is common."

    for module in (jd_parser, role_researcher, evidence_mapper, resume_drafter, evaluator, replanner, verifier):
        monkeypatch.setattr(module, "call_llm_json", fake_call_llm_json)
    monkeypatch.setattr(report_generator, "call_llm", fake_call_llm)
    monkeypatch.setattr(role_researcher, "search_role_info", fake_search)
    return calls


def test_pipeline_revises_once_then_verifies_and_removes_fabrication(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "output_dir", str(tmp_path))
    calls = _stub_llm(monkeypatch)

    state = new_state("offline1", load_demo_job_description(), candidate_data=load_demo_candidate(), max_revisions=3)
    final = asyncio.run(agent_graph.ainvoke(state, config={"recursion_limit": recursion_limit_for(3)}))

    assert final["current_agent"] == "done"
    assert final["error"] is None
    assert calls["ats"] == 2
    assert final["revision_count"] == 1

    history = final["revision_history"]
    assert [entry["passed"] for entry in history] == [False, True]
    assert history[1]["ats_score"] == 92 and history[1]["pages"] == 1

    verification = final["verification"]
    assert verification.removed_claims == [FABRICATED_BULLET]
    assert "Kafka" in final["resume_content"].skills_section
    assert verification.fabrication_detected is True
    assert verification.verified_claims == 9

    assert final["pdf_path"].endswith("resume_final.pdf") and os.path.exists(final["pdf_path"])
    with pymupdf.open(final["pdf_path"]) as doc:
        text = doc[0].get_text()
    assert "reducing data latency by 40%" in text
    assert "$5M" not in text

    assert final["evidence_report"] == "## Summary\nReport body"
    assert (tmp_path / "offline1" / "evidence_report.md").exists()

    agents = [(event.agent_name, event.status) for event in final["trace"]]
    assert ("Replanner", AgentStatus.COMPLETED) in agents
    assert not any(status == AgentStatus.FAILED for _, status in agents)


def test_pipeline_stops_when_profile_cannot_be_extracted(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "output_dir", str(tmp_path))
    _stub_llm(monkeypatch)

    state = new_state("offline2", load_demo_job_description(), candidate_data={"hobbies": "chess"}, max_revisions=1)

    async def empty_profile(system, user, temperature=0.2):
        return {"name": ""}

    from backend.agents import profile_analyzer
    monkeypatch.setattr(profile_analyzer, "call_llm_json", empty_profile)

    final = asyncio.run(agent_graph.ainvoke(state, config={"recursion_limit": recursion_limit_for(1)}))

    assert final["candidate_profile"] is None
    assert final["pdf_path"] is None
    assert "usable candidate profile" in final["error"]
    assert final["trace"][-1].agent_name == "Profile Analyzer"

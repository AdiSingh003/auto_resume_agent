from backend.agents.common import (
    build_resume_content,
    coerce_model,
    diff_resumes,
    pdf_safe,
    remove_claims,
    supported_by_source,
    to_score,
)
from backend.models.schemas import CandidateProfile, ParsedJD, SeniorityLevel


def test_to_score_coerces_llm_formats():
    assert to_score(85) == 85
    assert to_score(85.6) == 86
    assert to_score("72/100") == 72
    assert to_score("n/a") == 50
    assert to_score(140) == 100
    assert to_score(None, default=0) == 0


def test_coerce_model_handles_loose_llm_json():
    jd = coerce_model(ParsedJD, {
        "job_title": "Engineer",
        "seniority_level": "Senior",
        "required_skills": "Python\nDocker",
        "keywords": None,
        "unexpected": 1,
    })
    assert jd.seniority_level == SeniorityLevel.SENIOR
    assert jd.required_skills == ["Python", "Docker"]
    assert jd.keywords == []


def test_coerce_model_falls_back_to_default_on_invalid_enum():
    assert coerce_model(ParsedJD, {"seniority_level": "mid-senior"}).seniority_level == SeniorityLevel.MID


def test_coerce_model_coerces_nested_models_and_drops_junk():
    profile = coerce_model(CandidateProfile, {
        "name": "A",
        "experience": [{"company": "X", "achievements": "Did a thing"}, "junk"],
    })
    assert len(profile.experience) == 1
    assert profile.experience[0].achievements == ["Did a thing"]


def test_build_resume_content_normalizes_entries():
    resume = build_resume_content({
        "header_name": "Alex",
        "skills_section": {"Languages": ["Python", "Go"], "Cloud": "AWS, Docker"},
        "experience_entries": [{
            "company": "X", "title": "Dev", "start_date": "2020", "end_date": "2022",
            "achievements": "Built API\nCut latency 40%",
        }],
        "project_entries": [{"name": "P", "technologies": ["TS", "Python"], "highlights": ["1k users"]}],
    })
    assert resume.skills_section == ["Python", "Go", "AWS", "Docker"]
    assert resume.experience_entries[0]["dates"] == "2020 - 2022"
    assert resume.experience_entries[0]["bullets"] == ["Built API", "Cut latency 40%"]
    assert resume.project_entries[0]["technologies"] == "TS, Python"
    assert resume.project_entries[0]["bullets"] == ["1k users"]


def _resume():
    return build_resume_content({
        "header_name": "Alex",
        "professional_summary": "Backend engineer with 5 years of Python. Led a team of 40 engineers at Google.",
        "skills_section": ["Python", "Kafka", "Rust"],
        "experience_entries": [{
            "company": "TechFlow", "title": "Senior Engineer", "dates": "2022 - Present",
            "bullets": [
                "Architected a real-time pipeline with Python and Kafka, reducing latency by 40%.",
                "Increased revenue by $5M through a new recommendation engine.",
            ],
        }],
        "certifications": [{"name": "Google Cloud Professional Architect", "issuer": "Google"}],
    })


def test_remove_claims_strips_only_matching_content():
    resume = _resume()
    removed = remove_claims(resume, [
        "Increased revenue by $5M through a new recommendation engine",
        "Rust",
        "Led a team of 40 engineers at Google.",
        "Google Cloud Professional Architect",
    ])
    assert resume.experience_entries[0]["bullets"] == [
        "Architected a real-time pipeline with Python and Kafka, reducing latency by 40%."
    ]
    assert resume.experience_entries[0]["title"] == "Senior Engineer"
    assert resume.skills_section == ["Python", "Kafka"]
    assert resume.professional_summary == "Backend engineer with 5 years of Python."
    assert resume.certifications == []
    assert len(removed) == 4


def test_remove_claims_ignores_short_or_unrelated_claims():
    resume = _resume()
    assert remove_claims(resume, ["Python experience", "Go"]) == []
    assert resume.skills_section == ["Python", "Kafka", "Rust"]
    assert len(resume.experience_entries[0]["bullets"]) == 2


def test_diff_resumes_reports_changes():
    old, new = _resume(), _resume()
    new.experience_entries[0]["bullets"][1] = "Mentored 3 junior developers."
    new.skills_section = ["Python", "Kafka", "Docker"]
    changes = diff_resumes(old, new)
    assert changes["added"] == ["Mentored 3 junior developers."]
    assert changes["removed"] == ["Increased revenue by $5M through a new recommendation engine."]
    assert changes["skills_added"] == ["Docker"]
    assert changes["skills_removed"] == ["Rust"]
    assert changes["summary_changed"] is False
    assert diff_resumes(None, new)["added"] == []


def test_supported_by_source_matches_whole_terms_anywhere_in_source():
    source = (
        "Skills: Python, Go\n"
        "Experience: Senior Software Engineer at TechFlow\n"
        "  • Architected a real-time data processing pipeline using Python and Kafka."
    )
    assert supported_by_source("Kafka", source)
    assert supported_by_source("Skill: Real-time data processing", source)
    assert not supported_by_source("Event-driven architecture", source)
    assert not supported_by_source("Py", source)  # whole terms only


def test_pdf_safe_replaces_glyphs_missing_from_base_fonts():
    assert pdf_safe("real‑time data – ok") == "real-time data – ok"

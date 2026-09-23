import pymupdf
import pytest

from backend.agents.common import build_resume_content
from backend.api.routes import load_demo_candidate
from backend.config import settings
from backend.tools.pdf_renderer import render_resume_files, render_resume_html


def sample_resume():
    p = load_demo_candidate()
    return build_resume_content({
        "header_name": p["name"],
        "header_contact": " | ".join([p["email"], p["phone"], p["location"], p["linkedin"], p["github"]]),
        "professional_summary": p["summary"],
        "skills_section": p["skills"],
        "experience_entries": [
            {"company": e["company"], "title": e["title"], "dates": f"{e['start_date']} - {e['end_date']}",
             "bullets": e["achievements"]}
            for e in p["experience"]
        ],
        "project_entries": [
            {"name": x["name"], "technologies": x["technologies"], "url": x["url"], "bullets": x["highlights"]}
            for x in p["projects"]
        ],
        "education_entries": [
            {"institution": e["institution"], "degree": e["degree"], "date": e["graduation_date"],
             "highlights": e["highlights"]}
            for e in p["education"]
        ],
        "certifications": p["certifications"],
    })


@pytest.mark.parametrize("style", ["modern", "minimal"])
def test_render_produces_single_page_machine_readable_pdf(tmp_path, monkeypatch, style):
    monkeypatch.setattr(settings, "output_dir", str(tmp_path))

    result = render_resume_files(sample_resume(), style, "job1", "resume_v1")

    assert result["pages"] == 1
    with pymupdf.open(result["pdf_path"]) as doc:
        text = doc[0].get_text()
    assert "Alex Chen" in text
    assert "Architected a real-time data processing pipeline" in text
    assert "Associate" in text and "â€" not in text  # UTF-8 en dash survives rendering
    assert (tmp_path / "job1" / "resume_v1.html").exists()


def test_html_is_escaped_and_pdf_safe():
    resume = build_resume_content({
        "header_name": "<script>alert(1)</script>",
        "professional_summary": "Built real‑time systems",
        "skills_section": ["Python"],
    })
    html = render_resume_html(resume, "modern")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "real-time" in html


def test_unknown_template_falls_back_to_modern():
    html = render_resume_html(build_resume_content({"skills_section": ["Python"]}), "../../etc/passwd")
    assert 'class="resume modern"' in html

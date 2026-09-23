"""PDF Renderer — renders resume HTML via Jinja2 and converts it to PDF.

WeasyPrint is used when its native libraries (Pango/GTK) are available; otherwise
xhtml2pdf (pure Python) is used, which is the common case on Windows. The templates
use table-based layouts so they render identically in both engines and in a browser.
"""

import asyncio
import contextlib
import functools
import io
import os
import logging
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from backend.agents.common import pdf_safe
from backend.agents.state import AgentState
from backend.models.schemas import AgentTraceEvent, AgentStatus
from backend.config import settings

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"
TEMPLATE_STYLES = ("modern", "minimal")


@functools.lru_cache(maxsize=1)
def _weasyprint_html():
    """Return WeasyPrint's HTML class if its native dependencies load, else None."""
    try:
        # WeasyPrint prints a long banner when GTK/Pango are missing.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            from weasyprint import HTML
        return HTML
    except (ImportError, OSError) as e:
        logger.info("WeasyPrint unavailable (%s); using xhtml2pdf", type(e).__name__)
        return None


def pdf_engine_name() -> str:
    return "weasyprint" if _weasyprint_html() else "xhtml2pdf"


@functools.lru_cache(maxsize=1)
def _template_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )


def render_resume_html(resume_content, template_style: str = "modern") -> str:
    """Render resume content to a standalone HTML string (CSS inlined)."""
    if template_style not in TEMPLATE_STYLES:
        template_style = "modern"
    template = _template_env().get_template(f"{template_style}.html")
    css = (TEMPLATE_DIR / "styles.css").read_text(encoding="utf-8")

    return pdf_safe(template.render(
        css=css,
        name=resume_content.header_name,
        contact=resume_content.header_contact,
        summary=resume_content.professional_summary,
        skills=resume_content.skills_section,
        experiences=resume_content.experience_entries,
        projects=resume_content.project_entries,
        education=resume_content.education_entries,
        certifications=resume_content.certifications,
        additional=resume_content.additional_sections,
    ))


def html_to_pdf(html_content: str, output_path: str) -> str:
    """Convert standalone HTML to a PDF file."""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    weasy_html = _weasyprint_html()
    if weasy_html:
        weasy_html(string=html_content, base_url=str(TEMPLATE_DIR)).write_pdf(output_path)
        return output_path

    from xhtml2pdf import pisa

    with open(output_path, "wb") as result_file:
        status = pisa.CreatePDF(html_content, dest=result_file, encoding="utf-8")
    if status.err:
        raise RuntimeError(f"xhtml2pdf reported {status.err} error(s) rendering {output_path}")
    return output_path


def count_pdf_pages(pdf_path: str) -> int:
    import pymupdf

    with pymupdf.open(pdf_path) as doc:
        return doc.page_count


def render_resume_files(resume_content, template_style: str, job_id: str, stem: str) -> dict:
    """Render HTML + PDF for a resume into output/<job_id>/<stem>.{html,pdf}."""
    output_dir = os.path.join(settings.output_dir, job_id)
    os.makedirs(output_dir, exist_ok=True)

    html_content = render_resume_html(resume_content, template_style)
    html_path = os.path.join(output_dir, f"{stem}.html")
    pdf_path = os.path.join(output_dir, f"{stem}.pdf")

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    html_to_pdf(html_content, pdf_path)

    return {
        "pdf_path": pdf_path,
        "html_path": html_path,
        "pages": count_pdf_pages(pdf_path),
        "file_size_kb": round(os.path.getsize(pdf_path) / 1024, 1),
        "engine": pdf_engine_name(),
    }


async def render_pdf(state: AgentState) -> dict:
    """Render the resume content as a professional PDF."""
    start_time = datetime.now()
    trace_events = []

    trace_events.append(AgentTraceEvent(
        agent_name="PDF Renderer",
        status=AgentStatus.RUNNING,
        message="Rendering resume to professional PDF...",
    ))

    try:
        resume_content = state.get("resume_content")
        if not resume_content:
            raise ValueError("No resume content to render")

        template_style = state.get("template_style", "modern")
        job_id = state.get("job_id", "default")
        version = state.get("revision_count", 0) + 1

        # Rendering is CPU-bound; keep the event loop free for WebSocket traffic.
        result = await asyncio.to_thread(
            render_resume_files, resume_content, template_style, job_id, f"resume_v{version}"
        )

        duration = int((datetime.now() - start_time).total_seconds() * 1000)

        trace_events.append(AgentTraceEvent(
            agent_name="PDF Renderer",
            status=AgentStatus.COMPLETED,
            message=f"PDF generated: resume_v{version}.pdf ({result['file_size_kb']} KB, "
                    f"{result['pages']} page{'s' if result['pages'] != 1 else ''}). "
                    f"Template: {template_style}.",
            duration_ms=duration,
            details={**result, "template": template_style, "version": version},
        ))

        return {
            "pdf_path": result["pdf_path"],
            "current_agent": "evaluator",
            "trace": trace_events,
        }

    except Exception as e:
        logger.error("PDF Renderer failed: %s", e)
        trace_events.append(AgentTraceEvent(
            agent_name="PDF Renderer",
            status=AgentStatus.FAILED,
            message=f"PDF rendering failed: {str(e)}",
        ))
        return {
            "current_agent": "evaluator",
            "trace": trace_events,
            "error": str(e),
        }

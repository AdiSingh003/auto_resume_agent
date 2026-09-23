"""Shared helpers for agents: LLM-output coercion, resume serialization, draft diffs, claim removal."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from enum import Enum
from typing import get_args, get_origin

from pydantic import BaseModel

from backend.models.schemas import CandidateProfile, ResumeContent

SEVERITIES = ("low", "medium", "high", "critical")


# --- Scalar coercion -------------------------------------------------------

def to_score(value, default: int = 50) -> int:
    """Coerce an LLM-provided score (85, 85.5, "85", "85/100") into an int in [0, 100]."""
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, (int, float)):
        score = float(value)
    else:
        match = re.search(r"\d+(?:\.\d+)?", str(value))
        if not match:
            return default
        score = float(match.group())
    return max(0, min(100, int(round(score))))


def to_int(value, default: int = 0) -> int:
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, (int, float)):
        return int(value)
    match = re.search(r"-?\d+", str(value))
    return int(match.group()) if match else default


def as_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    if text in ("true", "yes", "y", "1"):
        return True
    if text in ("false", "no", "n", "0"):
        return False
    return default


def as_list(value) -> list[str]:
    """Coerce a string (newline/bullet separated) or list into a clean list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        parts = [p.strip().lstrip("•-*▸ ").strip() for p in value.split("\n")]
        return [p for p in parts if p]
    if isinstance(value, (list, tuple)):
        return [as_text(v) for v in value if v is not None and as_text(v)]
    return [str(value)]


def as_text(value) -> str:
    """Coerce a list or scalar into a display string."""
    if isinstance(value, (list, tuple)):
        return ", ".join(as_text(v) for v in value if v)
    if isinstance(value, dict):
        return ", ".join(f"{k}: {as_text(v)}" for k, v in value.items())
    return str(value if value is not None else "").strip()


def coerce_model(model_cls: type[BaseModel], data) -> BaseModel:
    """Build a pydantic model from loosely-typed LLM JSON, coercing each field to its declared type.

    LLMs routinely return "85" for ints, a string where a list is expected, or an enum
    value in the wrong case; strict validation would fail the whole agent over that.
    """
    if not isinstance(data, dict):
        data = {}
    values = {}
    for name, field in model_cls.model_fields.items():
        if data.get(name) is None:
            continue
        value = data[name]
        annotation = field.annotation
        origin, args = get_origin(annotation), get_args(annotation)

        if isinstance(annotation, type) and issubclass(annotation, Enum):
            normalized = as_text(value).lower()
            if normalized not in {member.value for member in annotation}:
                continue  # fall back to the field default
            value = normalized
        elif annotation is str:
            value = as_text(value)
        elif annotation is bool:
            value = as_bool(value, default=bool(field.default))
        elif annotation is int:
            value = to_int(value, default=field.default if isinstance(field.default, int) else 0)
        elif origin is list and args:
            item_type = args[0]
            items = value if isinstance(value, list) else []
            if item_type is str:
                value = as_list(value)
            elif isinstance(item_type, type) and issubclass(item_type, BaseModel):
                value = [coerce_model(item_type, item) for item in items if isinstance(item, dict)]
            elif item_type is dict:
                value = [item for item in items if isinstance(item, dict)]
        values[name] = value
    return model_cls(**values)


# --- Resume content ----------------------------------------------------------

def _flatten_skills(value) -> list[str]:
    """Skills may arrive as a list, a comma string, or a {category: [skills]} dict."""
    if isinstance(value, dict):
        skills = []
        for group in value.values():
            skills.extend(_flatten_skills(group))
        return skills
    if isinstance(value, str):
        return [s.strip() for s in re.split(r"[,\n]", value) if s.strip()]
    return as_list(value)


def build_resume_content(data: dict) -> ResumeContent:
    """Build a ResumeContent from loosely-shaped LLM JSON, normalizing every entry."""
    data = dict(data or {})
    values = {
        "header_name": as_text(data.get("header_name")),
        "header_contact": as_text(data.get("header_contact")),
        "professional_summary": as_text(data.get("professional_summary")),
        "skills_section": _flatten_skills(data.get("skills_section") or data.get("skills")),
    }
    for key in ("experience_entries", "project_entries", "education_entries", "certifications"):
        entries = data.get(key)
        values[key] = [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []
    sections = data.get("additional_sections")
    values["additional_sections"] = [
        {"title": as_text(s.get("title")), "content": as_text(s.get("content"))}
        for s in (sections if isinstance(sections, list) else [])
        if isinstance(s, dict)
    ]
    return normalize_resume_content(ResumeContent(**values))


def normalize_resume_content(resume: ResumeContent) -> ResumeContent:
    """Ensure entries use the keys and types the templates, evaluators, and verifier expect."""
    resume.experience_entries = [
        {
            "company": as_text(e.get("company")),
            "title": as_text(e.get("title")),
            "dates": as_text(
                e.get("dates")
                or " - ".join(str(x) for x in (e.get("start_date"), e.get("end_date")) if x)
            ),
            "location": as_text(e.get("location")),
            "bullets": as_list(e.get("bullets") or e.get("achievements")),
        }
        for e in resume.experience_entries
    ]
    resume.project_entries = [
        {
            "name": as_text(p.get("name")),
            "technologies": as_text(p.get("technologies")),
            "url": as_text(p.get("url")),
            "bullets": as_list(p.get("bullets") or p.get("highlights")),
        }
        for p in resume.project_entries
    ]
    resume.education_entries = [
        {
            "institution": as_text(e.get("institution")),
            "degree": as_text(e.get("degree")),
            "date": as_text(e.get("date") or e.get("graduation_date")),
            "highlights": as_list(e.get("highlights")),
        }
        for e in resume.education_entries
    ]
    resume.certifications = [
        {"name": as_text(c.get("name")), "issuer": as_text(c.get("issuer")), "date": as_text(c.get("date"))}
        for c in resume.certifications
    ]
    return resume


def resume_to_text(resume: ResumeContent | None) -> str:
    """Serialize resume content into plain text for LLM evaluation and verification."""
    if not resume:
        return ""
    lines = [
        f"Name: {resume.header_name}",
        f"Contact: {resume.header_contact}",
        f"Summary: {resume.professional_summary}",
        f"Skills: {', '.join(resume.skills_section)}",
        "",
    ]
    for exp in resume.experience_entries:
        lines.append(f"Experience: {exp.get('title', '')} at {exp.get('company', '')} ({exp.get('dates', '')})")
        lines.extend(f"  • {b}" for b in exp.get("bullets", []))
    for proj in resume.project_entries:
        lines.append(f"Project: {proj.get('name', '')} ({proj.get('technologies', '')})")
        lines.extend(f"  • {b}" for b in proj.get("bullets", []))
    for edu in resume.education_entries:
        lines.append(f"Education: {edu.get('degree', '')} from {edu.get('institution', '')} ({edu.get('date', '')})")
        lines.extend(f"  • {h}" for h in edu.get("highlights", []))
    for cert in resume.certifications:
        lines.append(f"Certification: {cert.get('name', '')} by {cert.get('issuer', '')} ({cert.get('date', '')})")
    for section in resume.additional_sections:
        lines.append(f"{section.title}: {section.content}")
    return "\n".join(lines)


def profile_to_text(profile: CandidateProfile | None) -> str:
    """Serialize the complete candidate profile — the source of truth for drafting and fact checks."""
    if not profile:
        return ""
    lines = [
        f"Name: {profile.name}",
        f"Email: {profile.email}",
        f"Phone: {profile.phone}",
        f"Location: {profile.location}",
    ]
    for label, value in (("LinkedIn", profile.linkedin), ("GitHub", profile.github), ("Portfolio", profile.portfolio)):
        if value:
            lines.append(f"{label}: {value}")
    lines += [f"Summary: {profile.summary}", f"Skills: {', '.join(profile.skills)}", ""]
    for exp in profile.experience:
        lines.append(f"Experience: {exp.title} at {exp.company} ({exp.start_date} - {exp.end_date})")
        if exp.description:
            lines.append(f"  Description: {exp.description}")
        lines.extend(f"  • {a}" for a in exp.achievements)
        if exp.technologies:
            lines.append(f"  Tech: {', '.join(exp.technologies)}")
    for proj in profile.projects:
        lines.append(f"Project: {proj.name}" + (f" ({proj.url})" if proj.url else ""))
        if proj.description:
            lines.append(f"  Description: {proj.description}")
        if proj.technologies:
            lines.append(f"  Tech: {', '.join(proj.technologies)}")
        lines.extend(f"  • {h}" for h in proj.highlights)
    for edu in profile.education:
        lines.append(f"Education: {edu.degree} in {edu.field} from {edu.institution} ({edu.graduation_date})")
        if edu.gpa:
            lines.append(f"  GPA: {edu.gpa}")
        lines.extend(f"  • {h}" for h in edu.highlights)
    for cert in profile.certifications:
        lines.append(f"Certification: {cert.name} by {cert.issuer} ({cert.date})")
    return "\n".join(lines)


def candidate_source_text(state: dict, max_raw_chars: int = 12_000) -> str:
    """Everything known to be true about the candidate: extracted profile plus any verbatim resume text."""
    text = profile_to_text(state.get("candidate_profile"))
    raw = (state.get("candidate_raw_text") or "").strip()
    if raw:
        text += f"\n\nORIGINAL RESUME TEXT (verbatim):\n{raw[:max_raw_chars]}"
    return text


# Characters LLMs emit that the PDF base fonts (WinAnsi encoding) cannot draw.
_PDF_UNSAFE_CHARS = str.maketrans({
    "‐": "-", "‑": "-", "‒": "-", "−": "-", "⁃": "-",
    " ": " ", " ": " ", " ": " ", " ": " ", " ": " ",
    "​": "", "⁠": "", "﻿": "",
    "▸": "-", "→": "->", "≈": "~", "≤": "<=", "≥": ">=",
})


def pdf_safe(text: str) -> str:
    return text.translate(_PDF_UNSAFE_CHARS)


# --- Revision diffs and claim removal ------------------------------------------

def _all_bullets(resume: ResumeContent) -> list[str]:
    bullets = []
    for entry in resume.experience_entries + resume.project_entries:
        bullets.extend(entry.get("bullets", []))
    return bullets


def diff_resumes(old: ResumeContent | None, new: ResumeContent) -> dict:
    """Summarize what changed between two drafts (for the revision-history timeline)."""
    if old is None:
        return {"added": [], "removed": [], "skills_added": [], "skills_removed": [], "summary_changed": False}
    old_bullets, new_bullets = _all_bullets(old), _all_bullets(new)
    old_skills, new_skills = set(old.skills_section), set(new.skills_section)
    return {
        "added": [b for b in new_bullets if b not in old_bullets],
        "removed": [b for b in old_bullets if b not in new_bullets],
        "skills_added": sorted(new_skills - old_skills),
        "skills_removed": sorted(old_skills - new_skills),
        "summary_changed": old.professional_summary.strip() != new.professional_summary.strip(),
    }


def _norm(text: str) -> str:
    text = re.sub(r"^(skills?|bullet|summary|project|experience)\s*:\s*", "", text.strip(), flags=re.I)
    text = re.sub(r"[^a-z0-9%+#. ]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip(" .")


def claim_matches(claim: str, candidate: str) -> bool:
    """Fuzzy match a verifier-reported claim against a piece of resume text."""
    c, t = _norm(claim), _norm(candidate)
    if not c or not t:
        return False
    if c == t:
        return True
    if min(len(c), len(t)) >= 25 and (c in t or t in c):
        return True
    return len(t) >= 25 and SequenceMatcher(None, c, t).ratio() >= 0.85


def supported_by_source(claim: str, source_text: str) -> bool:
    """True when the claim appears as a whole term/phrase (ignoring case and punctuation) in the source data."""
    normalized = _norm(claim)
    if not normalized:
        return False
    pattern = rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])"
    return re.search(pattern, _norm(source_text)) is not None


def remove_claims(resume: ResumeContent, claims: list[str]) -> list[str]:
    """Remove bullets, skills, certifications, and summary sentences matching unverified claims, in place.

    Returns the removed resume fragments. Entry headers (company, title, dates) are never
    removed — only the unsupported content within them.
    """
    removed: list[str] = []

    def keep(item: str) -> bool:
        if any(claim_matches(claim, item) for claim in claims):
            removed.append(item)
            return False
        return True

    for entry in resume.experience_entries + resume.project_entries:
        entry["bullets"] = [b for b in entry.get("bullets", []) if keep(b)]
    for edu in resume.education_entries:
        edu["highlights"] = [h for h in edu.get("highlights", []) if keep(h)]

    claim_norms = {_norm(c) for c in claims}
    kept_skills = []
    for skill in resume.skills_section:
        if _norm(skill) in claim_norms:
            removed.append(skill)
        else:
            kept_skills.append(skill)
    resume.skills_section = kept_skills

    kept_certs = []
    for cert in resume.certifications:
        name = cert.get("name", "")
        if name and (_norm(name) in claim_norms or any(claim_matches(c, name) for c in claims)):
            removed.append(name)
        else:
            kept_certs.append(cert)
    resume.certifications = kept_certs

    sentences = re.split(r"(?<=[.!?])\s+", resume.professional_summary.strip())
    resume.professional_summary = " ".join(s for s in sentences if s and keep(s))

    return removed

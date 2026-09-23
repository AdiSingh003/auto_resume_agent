"""Pydantic models for the Auto Resume Agent."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, Field


# --- Enums ---

class SeniorityLevel(str, Enum):
    INTERN = "intern"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    PRINCIPAL = "principal"
    EXECUTIVE = "executive"


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    REVISING = "revising"


# --- JD Parser Output ---

class ParsedJD(BaseModel):
    """Structured representation of a job description."""
    job_title: str = ""
    company_name: str = ""
    seniority_level: SeniorityLevel = SeniorityLevel.MID
    required_skills: list[str] = Field(default_factory=list)
    nice_to_have_skills: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    qualifications: list[str] = Field(default_factory=list)
    company_values: list[str] = Field(default_factory=list)
    industry: str = ""
    keywords: list[str] = Field(default_factory=list)


# --- Role Research Output ---

class RoleResearch(BaseModel):
    """Research findings about the target role and company."""
    industry_context: str = ""
    common_tech_stack: list[str] = Field(default_factory=list)
    company_culture_notes: str = ""
    role_expectations: list[str] = Field(default_factory=list)
    market_insights: str = ""


# --- Candidate Profile ---

class Experience(BaseModel):
    """A single work experience entry."""
    company: str = ""
    title: str = ""
    start_date: str = ""
    end_date: str = ""
    description: str = ""
    achievements: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)


class Project(BaseModel):
    """A single project entry."""
    name: str = ""
    description: str = ""
    technologies: list[str] = Field(default_factory=list)
    url: str = ""
    highlights: list[str] = Field(default_factory=list)


class Education(BaseModel):
    """A single education entry."""
    institution: str = ""
    degree: str = ""
    field: str = ""
    graduation_date: str = ""
    gpa: str = ""
    highlights: list[str] = Field(default_factory=list)


class Certification(BaseModel):
    """A certification entry."""
    name: str = ""
    issuer: str = ""
    date: str = ""
    url: str = ""


class CandidateProfile(BaseModel):
    """Complete candidate profile extracted from resume and supporting materials."""
    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin: str = ""
    github: str = ""
    portfolio: str = ""
    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)


# --- Evidence Mapping ---

class EvidenceLink(BaseModel):
    """Maps a JD requirement to specific candidate evidence."""
    requirement: str = ""
    candidate_evidence: list[str] = Field(default_factory=list)
    strength: str = "weak"  # weak, moderate, strong
    notes: str = ""


class EvidenceMap(BaseModel):
    """Complete mapping of JD requirements to candidate evidence."""
    matched_requirements: list[EvidenceLink] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    strongest_fits: list[str] = Field(default_factory=list)
    recommended_focus: list[str] = Field(default_factory=list)


# --- Resume Content ---

class ResumeSection(BaseModel):
    """A section of the tailored resume."""
    title: str = ""
    content: str = ""


class ResumeContent(BaseModel):
    """Complete tailored resume content."""
    header_name: str = ""
    header_contact: str = ""
    professional_summary: str = ""
    skills_section: list[str] = Field(default_factory=list)
    experience_entries: list[dict] = Field(default_factory=list)
    project_entries: list[dict] = Field(default_factory=list)
    education_entries: list[dict] = Field(default_factory=list)
    certifications: list[dict] = Field(default_factory=list)
    additional_sections: list[ResumeSection] = Field(default_factory=list)


# --- Evaluation ---

class EvaluationFeedback(BaseModel):
    """Single piece of evaluation feedback."""
    category: str = ""  # ats, formatting, factual
    issue: str = ""
    severity: str = "medium"  # low, medium, high, critical
    suggestion: str = ""


class EvaluationResult(BaseModel):
    """Combined evaluation scores and feedback."""
    ats_score: int = 0
    formatting_score: int = 0
    factual_consistency_score: int = 0
    overall_score: int = 0
    feedback: list[EvaluationFeedback] = Field(default_factory=list)
    passed: bool = False


# --- Revision ---

class RevisionInstruction(BaseModel):
    """Specific instruction for revising the resume."""
    target_section: str = ""
    action: str = ""  # rewrite, add, remove, reorder, rephrase
    details: str = ""
    priority: str = "medium"


class RevisionPlan(BaseModel):
    """Plan for revising the resume based on evaluation."""
    revision_instructions: list[RevisionInstruction] = Field(default_factory=list)
    focus_areas: list[str] = Field(default_factory=list)
    rationale: str = ""


# --- Verification ---

class ClaimVerification(BaseModel):
    """Verification result for a single claim."""
    claim: str = ""
    verified: bool = False
    evidence_source: str = ""
    notes: str = ""


class VerificationResult(BaseModel):
    """Complete verification of all claims in the resume."""
    total_claims: int = 0
    verified_claims: int = 0
    unverified_claims: list[ClaimVerification] = Field(default_factory=list)
    fabrication_detected: bool = False
    overall_trustworthy: bool = True
    removed_claims: list[str] = Field(default_factory=list)  # resume text stripped as unsupported


# --- Agent Trace ---

class AgentTraceEvent(BaseModel):
    """A single event in the agent execution trace."""
    agent_name: str = ""
    status: AgentStatus = AgentStatus.PENDING
    message: str = ""
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat()
    )
    details: Optional[dict] = None
    duration_ms: Optional[int] = None


# --- API Request/Response ---

class GenerateRequest(BaseModel):
    """Request to generate a tailored resume."""
    job_description: str = Field(max_length=50_000)
    candidate_data: Optional[dict] = None
    resume_text: Optional[str] = Field(default=None, max_length=100_000)
    use_demo_profile: bool = False
    template_style: Literal["modern", "minimal"] = "modern"


class JobStatus(BaseModel):
    """Status of a resume generation job."""
    job_id: str
    status: AgentStatus
    current_agent: str = ""
    revision_count: int = 0
    trace: list[AgentTraceEvent] = Field(default_factory=list)
    evaluation: Optional[EvaluationResult] = None
    pdf_ready: bool = False
    report_ready: bool = False

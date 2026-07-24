"""
fallback/schema.py — Tool-use schemas for Bedrock Converse API
==============================================================
Defines the precise JSON structures we force Amazon Nova to output.
"""


from pydantic import BaseModel, Field


class ExperienceEntry(BaseModel):
    role: str | None = Field(None, description="Job title or role")
    company: str | None = Field(None, description="Company or organization name")
    start: str | None = Field(None, description="Start date (e.g., 'Jan 2020', '2015')")
    end: str | None = Field(None, description="End date (e.g., 'Present', 'Dec 2022')")
    description: str | None = Field(None, description="Raw paragraph description (optional)")
    achievements: list[str] = Field(default_factory=list, description="Bullet points of achievements")


class EducationEntry(BaseModel):
    degree: str | None = Field(None, description="Degree name (e.g., 'Bachelor of Science in Computer Science')")
    institution: str | None = Field(None, description="University or school name")
    start: str | None = Field(None, description="Start date")
    end: str | None = Field(None, description="End date or expected graduation")
    grade: str | None = Field(None, description="GPA or grade")


class FallbackExtractionSchema(BaseModel):
    """
    The master schema for LLM extraction.
    We pass this to Bedrock as a tool, forcing the model to return this structure.
    """
    name: str | None = Field(None, description="Candidate's full name")
    email: str | None = Field(None, description="Email address")
    phone: str | None = Field(None, description="Phone number")
    linkedin: str | None = Field(None, description="LinkedIn URL or handle")
    github: str | None = Field(None, description="GitHub URL or handle")
    location: str | None = Field(None, description="City, State, or Country")
    
    summary: str | None = Field(None, description="Professional summary paragraph")
    skills: list[str] = Field(default_factory=list, description="List of technical/professional skills")
    
    experience: list[ExperienceEntry] = Field(default_factory=list, description="Employment history")
    education: list[EducationEntry] = Field(default_factory=list, description="Educational background")

    # We ask the model to provide a confidence score (0.0 to 1.0) for its extraction quality
    confidence: float = Field(
        ..., 
        description="Your confidence in the extracted data. 1.0 = perfect structured text, 0.5 = ambiguous/garbled, 0.0 = total guess."
    )

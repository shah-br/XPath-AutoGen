"""Pydantic models for pipeline data."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class DiscoverySource(str, Enum):
    STATIC = "static"
    SCROLL = "scroll"
    HOVER = "hover"
    EXPAND = "expand"
    FORM = "form"


class Section(str, Enum):
    HEADER = "Header"
    NAVIGATION = "Navigation"
    MAIN_CONTENT = "MainContent"
    SIDEBAR = "Sidebar"
    FORM = "Form"
    MODAL = "Modal"
    FOOTER = "Footer"
    OTHER = "Other"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ValidationStatus(str, Enum):
    VALID = "valid"
    REPAIRED = "repaired"
    INVALID = "invalid"


class RawElement(BaseModel):
    element_id: str
    tag: str
    element_type: str = ""
    text: str = ""
    aria_label: str = ""
    element_id_attr: str = Field(default="", alias="id")
    name: str = ""
    placeholder: str = ""
    role: str = ""
    data_testid: str = ""
    classes: str = ""
    href: str = ""
    dom_path: str = ""
    bbox_x: float = 0
    bbox_y: float = 0
    bbox_width: float = 0
    bbox_height: float = 0
    is_visible: bool = True
    is_enabled: bool = True
    discovery_source: DiscoverySource = DiscoverySource.STATIC

    model_config = {"populate_by_name": True}

    def fingerprint(self) -> str:
        if self.dom_path:
            return f"dom_path|{self.dom_path}"

        text_norm = " ".join(self.text.split())[:80].lower()

        return "|".join(
            [
                self.tag.lower(),
                self.element_id_attr,
                self.name,
                text_norm,
                self.role,
                self.data_testid,
                f"{int(self.bbox_x)}:{int(self.bbox_y)}",
            ]
        )


class NamedLocator(BaseModel):
    element_id: str
    element_name: str
    xpath: str
    confidence: Confidence = Confidence.MEDIUM
    rationale: str = ""
    section: Section = Section.OTHER
    tag: str = ""
    text: str = ""
    discovery_source: DiscoverySource = DiscoverySource.STATIC


class BrowserValidation(BaseModel):
    browser: str
    passed: bool
    element_count: int = 0
    error: str = ""


class ValidatedLocator(NamedLocator):
    browser_results: list[BrowserValidation] = Field(default_factory=list)
    overall_status: ValidationStatus = ValidationStatus.INVALID
    repair_note: str = ""

    @property
    def overall_pass(self) -> bool:
        return self.overall_status in (ValidationStatus.VALID, ValidationStatus.REPAIRED)


class JobStage(str, Enum):
    PENDING = "pending"
    EXTRACTING = "extracting"
    CLASSIFYING = "classifying"
    GENERATING = "generating"
    VALIDATING = "validating"
    EXPORTING = "exporting"
    COMPLETED = "completed"
    FAILED = "failed"


class ProgressEvent(BaseModel):
    stage: JobStage
    message: str
    pct: int = 0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class JobRequest(BaseModel):
    url: str
    enable_hidden_discovery: bool = True
    max_elements: int = 200
    browsers: list[str] = Field(default_factory=lambda: ["chromium", "firefox", "webkit"])


class JobSummary(BaseModel):
    job_id: str
    url: str
    status: JobStage
    total_elements: int = 0
    pass_count: int = 0
    pass_rate_pct: float = 0.0
    static_count: int = 0
    discovered_count: int = 0
    discovery_boost_pct: float = 0.0
    excel_path: str = ""
    error: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None


class JobState(BaseModel):
    summary: JobSummary
    events: list[ProgressEvent] = Field(default_factory=list)
    locators: list[ValidatedLocator] = Field(default_factory=list)
    page_title: str = ""


# LLM structured output schemas

class SectionAssignment(BaseModel):
    element_id: str
    section: str


class SectionBatchResponse(BaseModel):
    assignments: list[SectionAssignment]


class GeneratedLocator(BaseModel):
    element_id: str
    element_name: str
    xpath: str
    confidence: Literal["high", "medium", "low"]
    rationale: str


class GenerateBatchResponse(BaseModel):
    locators: list[GeneratedLocator]


class RepairResponse(BaseModel):
    xpath: str
    confidence: Literal["high", "medium", "low"]
    rationale: str

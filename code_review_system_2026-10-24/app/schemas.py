from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    service: str


class DashboardSummaryResponse(BaseModel):
    project_count: int
    scan_count: int
    completed_scan_count: int
    scan_finding_count: int
    high_risk_count: int
    medium_risk_count: int
    other_finding_count: int


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    language: str = Field(default="python", min_length=1, max_length=30)
    description: str | None = None
    source_path: str | None = Field(default=None, max_length=500)


class ProjectResponse(ProjectCreate):
    id: str
    created_at: datetime


class ScanCreate(BaseModel):
    project_id: str


class ScanResponse(BaseModel):
    id: str
    project_id: str
    status: Literal["created", "running", "completed", "failed"]
    created_at: datetime
    finding_count: int = 0
    error: str | None = None


class CodeAnalyzeRequest(BaseModel):
    file_path: str = Field(default="<input>", max_length=255)
    code: str = Field(..., min_length=1)


class FindingResponse(BaseModel):
    file_path: str
    line: int
    column: int
    rule_id: str
    message: str
    severity: str


class CodeAnalyzeResponse(BaseModel):
    analyzer: str
    finding_count: int
    findings: list[FindingResponse]


class ReviewChange(BaseModel):
    status: Literal["new", "persistent", "absent"]
    finding: FindingResponse


class ReviewComparison(BaseModel):
    available: bool = False
    baseline_id: str | None = None
    baseline_created_at: datetime | None = None
    new_count: int = 0
    persistent_count: int = 0
    absent_count: int = 0
    explanation: str
    changes: list[ReviewChange] = Field(default_factory=list)


class ReviewHistoryItem(BaseModel):
    id: str
    file_path: str
    created_at: datetime
    finding_count: int
    high_risk_count: int
    line_count: int
    new_count: int | None = None
    persistent_count: int | None = None
    absent_count: int | None = None


class ReviewHistoryDetail(ReviewHistoryItem):
    code: str
    analysis: CodeAnalyzeResponse
    comparison: ReviewComparison


class ReviewHistoryList(BaseModel):
    total: int
    items: list[ReviewHistoryItem]


class RepairRequest(BaseModel):
    file_path: str = Field(default="<input>", max_length=255)
    code: str = Field(..., min_length=1)
    rule_id: str = Field(..., min_length=1)
    line: int = Field(..., ge=1)
    column: int = Field(..., ge=0)


class RepairResponse(BaseModel):
    status: Literal["available", "manual"]
    rule_id: str
    explanation: str
    candidate_code: str | None
    target_resolved: bool
    before_count: int
    after_count: int | None
    remaining_findings: list[FindingResponse]
    warnings: list[str]


class LLMReviewRequest(BaseModel):
    provider: Literal["openai-compatible", "codex"] = "codex"
    file_path: str = Field(default="<input>", max_length=255)
    code: str = Field(..., min_length=1)
    context: str = Field(default="", max_length=10000)
    static_findings: list[dict] = Field(default_factory=list)


class LLMReviewResponse(BaseModel):
    provider: str
    model: str
    result: dict


class GitHubPRReviewRequest(BaseModel):
    pr_url: str = Field(..., min_length=1, max_length=500)
    provider: Literal["openai-compatible", "codex"] = "codex"
    include_llm: bool = False
    max_files: int = Field(default=30, ge=1, le=100)
    max_llm_files: int = Field(default=5, ge=0, le=10)
    post_comments: bool = False


class GitHubPRFileReview(BaseModel):
    path: str
    status: str
    additions: int = 0
    deletions: int = 0
    analyzed: bool
    findings: list[FindingResponse] = Field(default_factory=list)
    skipped_reason: str | None = None
    llm_review: dict | None = None
    llm_error: str | None = None


class GitHubPRReviewResponse(BaseModel):
    pr_url: str
    repository: str
    number: int
    title: str
    state: str
    head_sha: str
    base_branch: str
    changed_file_count: int
    analyzed_file_count: int
    skipped_file_count: int
    finding_count: int
    files: list[GitHubPRFileReview]
    warnings: list[str] = Field(default_factory=list)

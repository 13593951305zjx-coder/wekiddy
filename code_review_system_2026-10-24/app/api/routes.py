import sqlite3

from fastapi import APIRouter, HTTPException, Query, status

from app.github.client import GitHubClientError
from app.schemas import (
    HealthResponse,
    CodeAnalyzeRequest,
    CodeAnalyzeResponse,
    DashboardSummaryResponse,
    FindingResponse,
    GitHubPRReviewRequest,
    GitHubPRReviewResponse,
    LLMReviewRequest,
    LLMReviewResponse,
    ProjectCreate,
    ProjectResponse,
    RepairRequest,
    RepairResponse,
    ReviewHistoryDetail,
    ReviewHistoryList,
    ScanCreate,
    ScanResponse,
)
from app.services.project_service import ProjectService
from app.services.scan_service import ScanService
from app.services.analysis_service import AnalysisService
from app.services.llm_review_service import LLMReviewService
from app.repair.service import RepairService
from app.services.github_review_service import GitHubPRReviewService
from app.services.review_history_service import ReviewHistoryService


router = APIRouter()
project_service = ProjectService()
scan_service = ScanService(project_service=project_service)
analysis_service = AnalysisService()
llm_review_service = LLMReviewService()
repair_service = RepairService()
github_review_service = GitHubPRReviewService()
review_history_service = ReviewHistoryService()


@router.get("/health", response_model=HealthResponse, tags=["系统"])
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="code-review-system")


@router.get("/dashboard/summary", response_model=DashboardSummaryResponse, tags=["统计"])
def dashboard_summary() -> DashboardSummaryResponse:
    scans = scan_service.list_all()
    completed = [scan for scan in scans if scan.status == "completed"]
    findings = [
        finding
        for scan in completed
        for finding in scan_service.get_findings(scan.id)
    ]
    high_risk_count = sum(
        finding.severity.upper() in {"HIGH", "CRITICAL"} for finding in findings
    )
    medium_risk_count = sum(
        finding.severity.upper() == "MEDIUM" for finding in findings
    )
    return DashboardSummaryResponse(
        project_count=len(project_service.list_all()),
        scan_count=len(scans),
        completed_scan_count=len(completed),
        scan_finding_count=len(findings),
        high_risk_count=high_risk_count,
        medium_risk_count=medium_risk_count,
        other_finding_count=len(findings) - high_risk_count - medium_risk_count,
    )


@router.post("/analysis/python", response_model=CodeAnalyzeResponse, tags=["代码分析"])
def analyze_python_code(payload: CodeAnalyzeRequest) -> CodeAnalyzeResponse:
    return analysis_service.analyze_python(payload)


@router.post("/reviews", response_model=ReviewHistoryDetail, tags=["审查历史"])
def analyze_and_save_review(payload: CodeAnalyzeRequest) -> ReviewHistoryDetail:
    try:
        return review_history_service.record(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (sqlite3.Error, OSError) as exc:
        raise HTTPException(status_code=503, detail="无法保存审查历史，请检查本地数据目录是否可写。") from exc


@router.get("/reviews", response_model=ReviewHistoryList, tags=["审查历史"])
def list_review_history(
    file_path: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ReviewHistoryList:
    try:
        return review_history_service.list_all(file_path, limit, offset)
    except (sqlite3.Error, OSError) as exc:
        raise HTTPException(status_code=503, detail="无法读取本地审查历史，请检查数据目录。") from exc


@router.get("/reviews/{review_id}", response_model=ReviewHistoryDetail, tags=["审查历史"])
def get_review_history(review_id: str) -> ReviewHistoryDetail:
    try:
        review = review_history_service.get(review_id)
    except (sqlite3.Error, OSError) as exc:
        raise HTTPException(status_code=503, detail="无法读取本地审查历史，请检查数据目录。") from exc
    if review is None:
        raise HTTPException(status_code=404, detail="审查记录不存在")
    return review


@router.post("/repair/python", response_model=RepairResponse, tags=["漏洞修复"])
def propose_python_repair(payload: RepairRequest) -> RepairResponse:
    try:
        return repair_service.propose(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/review/llm", response_model=LLMReviewResponse, tags=["大语言模型审查"])
def review_with_llm(payload: LLMReviewRequest) -> LLMReviewResponse:
    try:
        return llm_review_service.review(payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/github/pr/review",
    response_model=GitHubPRReviewResponse,
    tags=["GitHub PR 审查"],
)
def review_github_pull_request(payload: GitHubPRReviewRequest) -> GitHubPRReviewResponse:
    try:
        return github_review_service.review(payload)
    except GitHubClientError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["项目"],
)
def create_project(payload: ProjectCreate) -> ProjectResponse:
    return project_service.create(payload)


@router.get("/projects", response_model=list[ProjectResponse], tags=["项目"])
def list_projects() -> list[ProjectResponse]:
    return project_service.list_all()


@router.post(
    "/scans",
    response_model=ScanResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["扫描"],
)
def create_scan(payload: ScanCreate) -> ScanResponse:
    try:
        return scan_service.create(payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/scans/{scan_id}", response_model=ScanResponse, tags=["扫描"])
def get_scan(scan_id: str) -> ScanResponse:
    scan = scan_service.get(scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="扫描任务不存在")
    return scan


@router.get(
    "/scans/{scan_id}/findings",
    response_model=list[FindingResponse],
    tags=["扫描"],
)
def get_scan_findings(scan_id: str) -> list[FindingResponse]:
    scan = scan_service.get(scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="扫描任务不存在")
    return [FindingResponse(**finding.__dict__) for finding in scan_service.get_findings(scan_id)]

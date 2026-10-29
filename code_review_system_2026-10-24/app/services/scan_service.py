from datetime import datetime, timezone
from uuid import uuid4

from app.schemas import ScanCreate, ScanResponse
from app.analyzers.base import Finding
from app.analyzers.python_analyzer import PythonAnalyzer
from app.services.project_service import ProjectService


class ScanService:
    """扫描任务服务。

    提供同步扫描入口；后续可以将分析调用迁移到异步任务队列。
    """

    def __init__(self, project_service: ProjectService) -> None:
        self.project_service = project_service
        self._scans: dict[str, ScanResponse] = {}
        self._findings: dict[str, list[Finding]] = {}
        self._python_analyzer = PythonAnalyzer()

    def create(self, payload: ScanCreate) -> ScanResponse:
        project = self.project_service.get(payload.project_id)
        if project is None:
            raise ValueError("项目不存在")

        scan = ScanResponse(
            id=str(uuid4()),
            project_id=payload.project_id,
            status="created" if not project.source_path else "running",
            created_at=datetime.now(timezone.utc),
        )

        if project.source_path:
            try:
                if project.language.lower() != "python":
                    raise ValueError("当前第一版只支持 Python 项目")
                findings = self._python_analyzer.analyze(project.source_path)
                self._findings[scan.id] = findings
                scan.status = "completed"
                scan.finding_count = len(findings)
            except (FileNotFoundError, ValueError, OSError) as exc:
                scan.status = "failed"
                scan.error = str(exc)

        self._scans[scan.id] = scan
        return scan

    def get(self, scan_id: str) -> ScanResponse | None:
        return self._scans.get(scan_id)

    def list_all(self) -> list[ScanResponse]:
        return list(self._scans.values())

    def get_findings(self, scan_id: str) -> list[Finding]:
        return self._findings.get(scan_id, [])

from app.analyzers.python_analyzer import PythonAnalyzer
from app.schemas import CodeAnalyzeRequest, CodeAnalyzeResponse, FindingResponse


class AnalysisService:
    """统一管理代码分析器的业务服务。"""

    def __init__(self) -> None:
        self.python_analyzer = PythonAnalyzer()

    def analyze_python(self, payload: CodeAnalyzeRequest) -> CodeAnalyzeResponse:
        findings = self.python_analyzer.analyze_source(payload.code, payload.file_path)
        return CodeAnalyzeResponse(
            analyzer="python-ast",
            finding_count=len(findings),
            findings=[FindingResponse(**finding.__dict__) for finding in findings],
        )

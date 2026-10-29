from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Finding:
    """统一的漏洞发现结果格式。"""

    file_path: str
    line: int
    rule_id: str
    message: str
    severity: str = "INFO"
    column: int = 0


class BaseAnalyzer(ABC):
    """所有静态分析器都遵循的接口。"""

    @abstractmethod
    def analyze(self, project_path: str) -> list[Finding]:
        raise NotImplementedError

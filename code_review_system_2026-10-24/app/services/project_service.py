from datetime import datetime, timezone
from uuid import uuid4

from app.schemas import ProjectCreate, ProjectResponse


class ProjectService:
    """项目管理服务。

    当前使用内存存储，后续只需替换此处的存储实现即可接入数据库。
    """

    def __init__(self) -> None:
        self._projects: dict[str, ProjectResponse] = {}

    def create(self, payload: ProjectCreate) -> ProjectResponse:
        project = ProjectResponse(
            id=str(uuid4()),
            name=payload.name,
            language=payload.language,
            description=payload.description,
            source_path=payload.source_path,
            created_at=datetime.now(timezone.utc),
        )
        self._projects[project.id] = project
        return project

    def list_all(self) -> list[ProjectResponse]:
        return list(self._projects.values())

    def exists(self, project_id: str) -> bool:
        return project_id in self._projects

    def get(self, project_id: str) -> ProjectResponse | None:
        return self._projects.get(project_id)

from app.services.project_service import ProjectService
from app.services.scan_service import ScanService
from app.schemas import ProjectCreate, ScanCreate


def test_project_and_scan_skeleton() -> None:
    projects = ProjectService()
    scans = ScanService(project_service=projects)

    project = projects.create(ProjectCreate(name="demo"))
    scan = scans.create(ScanCreate(project_id=project.id))

    assert project.name == "demo"
    assert scan.project_id == project.id
    assert scan.status == "created"

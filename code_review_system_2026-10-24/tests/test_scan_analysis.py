from pathlib import Path

from app.schemas import ProjectCreate, ScanCreate
from app.services.project_service import ProjectService
from app.services.scan_service import ScanService


def test_scan_python_project(tmp_path: Path) -> None:
    source_file = tmp_path / "demo.py"
    source_file.write_text("import os\nos.system(user_input)\n", encoding="utf-8")

    projects = ProjectService()
    scans = ScanService(project_service=projects)
    project = projects.create(
        ProjectCreate(name="demo", source_path=str(tmp_path))
    )

    scan = scans.create(ScanCreate(project_id=project.id))

    assert scan.status == "completed"
    assert scan.finding_count == 1
    assert scans.get_findings(scan.id)[0].rule_id == "PY-CMD-001"

from app.api import routes
from app.analyzers.base import Finding
from app.schemas import ProjectCreate, ScanCreate
from app.services.project_service import ProjectService
from app.services.scan_service import ScanService


def test_dashboard_summary_counts_only_completed_scan_findings(tmp_path, monkeypatch):
    source = tmp_path / "demo.py"
    source.write_text(
        "import os\nimport yaml\nos.system(user_input)\nyaml.load(stream)\n",
        encoding="utf-8",
    )
    projects = ProjectService()
    scans = ScanService(project_service=projects)
    monkeypatch.setattr(routes, "project_service", projects)
    monkeypatch.setattr(routes, "scan_service", scans)

    completed_project = projects.create(ProjectCreate(name="completed", source_path=str(source)))
    pending_project = projects.create(ProjectCreate(name="pending"))
    failed_project = projects.create(
        ProjectCreate(name="failed", source_path=str(tmp_path / "missing"))
    )
    assert scans.create(ScanCreate(project_id=completed_project.id)).status == "completed"
    assert scans.create(ScanCreate(project_id=pending_project.id)).status == "created"
    assert scans.create(ScanCreate(project_id=failed_project.id)).status == "failed"

    assert routes.dashboard_summary().model_dump() == {
        "project_count": 3,
        "scan_count": 3,
        "completed_scan_count": 1,
        "scan_finding_count": 2,
        "high_risk_count": 1,
        "medium_risk_count": 1,
        "other_finding_count": 0,
    }


def test_dashboard_summary_classifies_other_severities(tmp_path, monkeypatch):
    source = tmp_path / "demo.py"
    source.write_text("pass\n", encoding="utf-8")
    projects = ProjectService()
    scans = ScanService(project_service=projects)
    monkeypatch.setattr(routes, "project_service", projects)
    monkeypatch.setattr(routes, "scan_service", scans)
    monkeypatch.setattr(
        scans._python_analyzer,
        "analyze",
        lambda path: [
            Finding(file_path=path, line=index, rule_id="TEST", message="issue", severity=severity)
            for index, severity in enumerate(
                ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"], start=1
            )
        ],
    )
    project = projects.create(ProjectCreate(name="severity test", source_path=str(source)))
    scan = scans.create(ScanCreate(project_id=project.id))

    assert scan.status == "completed"
    summary = routes.dashboard_summary()
    assert summary.scan_finding_count == 5
    assert summary.high_risk_count == 2
    assert summary.medium_risk_count == 1
    assert summary.other_finding_count == 2

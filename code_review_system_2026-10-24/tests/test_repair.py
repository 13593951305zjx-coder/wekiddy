import ast

import pytest
from fastapi import HTTPException

from app.analyzers.python_analyzer import PythonAnalyzer
from app.api.routes import propose_python_repair
from app.repair.service import RepairService
from app.schemas import RepairRequest


def _request(code: str, rule_id: str, occurrence: int = 0) -> RepairRequest:
    findings = [
        finding
        for finding in PythonAnalyzer().analyze_source(code, "example.py")
        if finding.rule_id == rule_id
    ]
    finding = findings[occurrence]
    return RepairRequest(
        file_path="example.py",
        code=code,
        rule_id=rule_id,
        line=finding.line,
        column=finding.column,
    )


def test_proposal_rewrites_only_selected_yaml_call_and_preserves_other_findings() -> None:
    code = (
        "import yaml\n"
        "password = 'demo'\n"
        "first = yaml.load(one)  # comment\n"
        "second = yaml.load(two)\n"
    )
    result = RepairService().propose(_request(code, "PY-DESERIALIZE-002", 1))

    assert result.status == "available"
    assert result.candidate_code == code.replace("yaml.load(two)", "yaml.safe_load(two)")
    assert result.before_count == 3
    assert result.after_count == 2
    assert result.target_resolved is True
    assert {finding.rule_id for finding in result.remaining_findings} == {
        "PY-SECRET-001",
        "PY-DESERIALIZE-002",
    }
    assert [(finding.line, finding.column) for finding in result.remaining_findings if finding.rule_id == "PY-DESERIALIZE-002"] == [(3, 8)]
    ast.parse(result.candidate_code)


def test_rewrite_handles_utf8_byte_columns_and_keeps_crlf() -> None:
    code = "import yaml\r\n结果 = yaml.load(data)\r\n"
    result = RepairService().propose(_request(code, "PY-DESERIALIZE-002"))

    assert result.status == "available"
    assert result.candidate_code == "import yaml\r\n结果 = yaml.safe_load(data)\r\n"
    assert result.after_count == 0


def test_unsupported_rule_returns_manual_without_modifying_code() -> None:
    code = "import os\nos.system(command)\n"
    result = RepairService().propose(_request(code, "PY-CMD-001"))

    assert result.status == "manual"
    assert result.candidate_code is None
    assert result.target_resolved is False
    assert result.before_count == 1
    assert result.after_count is None
    assert len(result.remaining_findings) == 1


@pytest.mark.parametrize(
    "code",
    [
        "import yaml\nvalue = yaml.load(data, None)\n",
        "import yaml\nvalue = yaml.load(data, **options)\n",
        "import yaml\ndef parse(yaml, data):\n    return yaml.load(data)\n",
        "value = yaml.load(data)\n",
        "def parse(data):\n    import yaml\n    return yaml.load(data)\n",
        "value = yaml.load(data)\nimport yaml\n",
    ],
)
def test_unsafe_or_ambiguous_yaml_calls_need_manual_review(code: str) -> None:
    result = RepairService().propose(_request(code, "PY-DESERIALIZE-002"))

    assert result.status == "manual"
    assert result.candidate_code is None
    assert result.after_count is None


def test_invalid_target_is_rejected_by_service_and_route() -> None:
    payload = RepairRequest(
        file_path="example.py",
        code="import yaml\nvalue = yaml.load(data)\n",
        rule_id="PY-DESERIALIZE-002",
        line=2,
        column=0,
    )

    with pytest.raises(ValueError, match="告警不存在"):
        RepairService().propose(payload)
    with pytest.raises(HTTPException) as exc_info:
        propose_python_repair(payload)
    assert exc_info.value.status_code == 422
    assert "告警不存在" in exc_info.value.detail


def test_route_returns_repair_response_for_valid_target() -> None:
    payload = _request("import yaml\nvalue = yaml.load(data)\n", "PY-DESERIALIZE-002")

    result = propose_python_repair(payload)

    assert result.status == "available"
    assert result.candidate_code == "import yaml\nvalue = yaml.safe_load(data)\n"
    assert result.remaining_findings == []

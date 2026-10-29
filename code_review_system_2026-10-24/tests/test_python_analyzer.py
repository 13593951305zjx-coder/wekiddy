from app.analyzers.python_analyzer import PythonAnalyzer
import pytest


def test_python_analyzer_finds_dangerous_calls_and_secret() -> None:
    code = '''
import os
password = "demo-password"
os.system(user_input)
result = eval(expression)
'''

    findings = PythonAnalyzer().analyze_source(code, "demo.py")
    rule_ids = {finding.rule_id for finding in findings}

    assert {"PY-SECRET-001", "PY-CMD-001", "PY-EVAL-001"}.issubset(rule_ids)


def test_python_analyzer_reports_syntax_error() -> None:
    findings = PythonAnalyzer().analyze_source("def broken(:", "broken.py")

    assert len(findings) == 1
    assert findings[0].rule_id == "PY-SYNTAX"


@pytest.mark.parametrize(
    ("code", "line"),
    [
        ('cursor.execute(f"SELECT * FROM users WHERE name = {name}")', 1),
        ('cursor.executemany("UPDATE users SET name = " + name, rows)', 1),
        ('cursor.execute("SELECT " + table + " WHERE id = " + user_id)', 1),
    ],
)
def test_sql_rule_flags_direct_dynamic_queries(code: str, line: int) -> None:
    findings = PythonAnalyzer().analyze_source(code, "database.py")

    assert [(finding.rule_id, finding.severity, finding.line) for finding in findings] == [
        ("PY-SQL-001", "HIGH", line)
    ]


@pytest.mark.parametrize(
    "code",
    [
        'cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))',
        'cursor.execute("SELECT " + "* FROM users")',
        'cursor.execute(query)',
        'logger.execute(f"message: {name}")',
        'cursor.execute("SELECT * FROM users WHERE id = %s" % user_id)',
    ],
)
def test_sql_rule_skips_queries_without_direct_dynamic_interpolation(code: str) -> None:
    findings = PythonAnalyzer().analyze_source(code)

    assert all(finding.rule_id != "PY-SQL-001" for finding in findings)


@pytest.mark.parametrize(
    "code",
    [
        'import requests\nrequests.get(url, verify=False)',
        'import requests as http\nhttp.post(url, verify=False)',
        'import requests\nsession = requests.Session()\nsession.request("GET", url, verify=False)',
        'from requests import Session as HttpSession\nsession = HttpSession()\nsession.put(url, verify=False)',
        'import requests\nrequests.Session().delete(url, verify=False)',
    ],
)
def test_tls_rule_flags_requests_calls_disabling_verification(code: str) -> None:
    findings = PythonAnalyzer().analyze_source(code, "client.py")

    tls_findings = [finding for finding in findings if finding.rule_id == "PY-TLS-001"]
    assert len(tls_findings) == 1
    assert tls_findings[0].severity == "MEDIUM"


@pytest.mark.parametrize(
    "code",
    [
        'client.get(url, verify=False)',
        'import requests\nrequests.get(url, verify=True)',
        'import requests\nrequests.get(url, verify=setting)',
        'import requests\nrequests.get(url, timeout=5)',
        'import requests\nrequests = custom_client\nrequests.get(url, verify=False)',
        'import requests\nsession = requests.Session()\nsession = custom_client\nsession.get(url, verify=False)',
    ],
)
def test_tls_rule_skips_uncertain_or_verified_calls(code: str) -> None:
    findings = PythonAnalyzer().analyze_source(code)

    assert all(finding.rule_id != "PY-TLS-001" for finding in findings)

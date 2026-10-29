"""Conservative, in-memory repair proposals for selected static findings."""

import ast

from app.analyzers.base import Finding
from app.analyzers.python_analyzer import PythonAnalyzer
from app.schemas import FindingResponse, RepairRequest, RepairResponse


RECHECK_WARNING = "已用 Python AST 重新检查候选代码；静态检查不能证明运行行为正确，请审阅并运行项目测试。"


class RepairService:
    def __init__(self) -> None:
        self.analyzer = PythonAnalyzer()

    def propose(self, payload: RepairRequest) -> RepairResponse:
        original = self.analyzer.analyze_source(payload.code, payload.file_path)
        target = (payload.rule_id, payload.line, payload.column)
        if not any(self._identity(finding) == target for finding in original):
            raise ValueError("指定的告警不存在于提交的代码中，请重新分析后选择告警。")

        if payload.rule_id != "PY-DESERIALIZE-002":
            return self._manual(
                payload, original, "该规则需要结合输入来源和程序行为判断，暂不提供自动改写。"
            )

        tree = ast.parse(payload.code, filename=payload.file_path)
        if not self._has_unshadowed_yaml_import(tree, payload.line):
            return self._manual(
                payload,
                original,
                "无法确认 yaml 名称始终指向 PyYAML 模块，请人工检查后修复。",
            )

        call = next(
            (
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and (node.lineno, node.col_offset) == (payload.line, payload.column)
                and PythonAnalyzer._call_name(node.func) == "yaml.load"
            ),
            None,
        )
        if call is None or len(call.args) != 1 or call.keywords or isinstance(call.args[0], ast.Starred):
            return self._manual(
                payload,
                original,
                "仅支持参数明确的 yaml.load(stream) 调用；其他调用形式需要人工确认。",
            )

        candidate = self._replace_attribute(payload.code, call.func)
        if candidate is None:
            return self._manual(
                payload, original, "无法精确定位 yaml.load 的函数名，请人工修改。"
            )

        remaining = self.analyzer.analyze_source(candidate, payload.file_path)
        resolved = not any(self._identity(finding) == target for finding in remaining)
        if not resolved or any(finding.rule_id == "PY-SYNTAX" for finding in remaining):
            return self._manual(
                payload, original, "候选代码未通过目标告警和语法复查，请人工修改。"
            )

        return RepairResponse(
            status="available",
            rule_id=payload.rule_id,
            explanation="将所选 yaml.load(stream) 改为 yaml.safe_load(stream)，减少不安全反序列化风险。",
            candidate_code=candidate,
            target_resolved=True,
            before_count=len(original),
            after_count=len(remaining),
            remaining_findings=self._responses(remaining),
            warnings=[
                "safe_load 仅支持安全 YAML 类型；若原代码依赖自定义对象标签，需要人工调整。",
                RECHECK_WARNING,
            ],
        )

    @staticmethod
    def _identity(finding: Finding) -> tuple[str, int, int]:
        return finding.rule_id, finding.line, finding.column

    @staticmethod
    def _responses(findings: list[Finding]) -> list[FindingResponse]:
        return [FindingResponse(**finding.__dict__) for finding in findings]

    def _manual(
        self, payload: RepairRequest, original: list[Finding], explanation: str
    ) -> RepairResponse:
        return RepairResponse(
            status="manual",
            rule_id=payload.rule_id,
            explanation=explanation,
            candidate_code=None,
            target_resolved=False,
            before_count=len(original),
            after_count=None,
            remaining_findings=self._responses(original),
            warnings=["未生成候选代码；请人工审查后运行项目测试。"],
        )

    @staticmethod
    def _has_unshadowed_yaml_import(tree: ast.Module, call_line: int) -> bool:
        # Require an unconditional module-level import. A nested or conditional
        # import does not establish what `yaml` means at the selected call.
        has_import = any(
            isinstance(node, ast.Import)
            and node.lineno < call_line
            and any(alias.name == "yaml" and alias.asname in (None, "yaml") for alias in node.names)
            for node in tree.body
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    local_name = alias.asname or alias.name.split(".")[0]
                    if local_name == "yaml":
                        if alias.name != "yaml" or alias.asname not in (None, "yaml"):
                            return False
            elif isinstance(node, ast.ImportFrom):
                if any((alias.asname or alias.name) == "yaml" for alias in node.names):
                    return False
            elif isinstance(node, ast.Name):
                if node.id == "yaml" and isinstance(node.ctx, (ast.Store, ast.Del)):
                    return False
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name == "yaml":
                    return False
            elif isinstance(node, ast.arg):
                if node.arg == "yaml":
                    return False
            elif isinstance(node, ast.ExceptHandler):
                if node.name == "yaml":
                    return False
            elif isinstance(node, ast.MatchAs):
                if node.name == "yaml":
                    return False
            elif isinstance(node, ast.MatchStar):
                if node.name == "yaml":
                    return False
            elif isinstance(node, ast.MatchMapping):
                if node.rest == "yaml":
                    return False
        return has_import

    @staticmethod
    def _replace_attribute(source: str, function: ast.expr) -> str | None:
        if not isinstance(function, ast.Attribute) or function.attr != "load":
            return None
        if function.end_lineno is None or function.end_col_offset is None:
            return None

        # AST columns are UTF-8 byte offsets. Edit only the four bytes occupied
        # by the attribute name; leave all surrounding whitespace intact.
        lines = source.encode("utf-8").splitlines(keepends=True)
        line_index = function.end_lineno - 1
        if line_index >= len(lines):
            return None
        end = sum(len(line) for line in lines[:line_index]) + function.end_col_offset
        start = end - len(b"load")
        encoded = source.encode("utf-8")
        if start < 0 or encoded[start:end] != b"load":
            return None
        return (encoded[:start] + b"safe_load" + encoded[end:]).decode("utf-8")

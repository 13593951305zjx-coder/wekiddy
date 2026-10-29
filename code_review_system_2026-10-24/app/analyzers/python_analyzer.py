import ast
import re
from pathlib import Path

from app.analyzers.base import BaseAnalyzer, Finding


class PythonAnalyzer(BaseAnalyzer):
    """基于 Python AST 的轻量级静态分析器。

    该版本只覆盖少量高价值规则，目的是先建立统一的分析器接口，
    后续可以在不改变 API 的情况下增加更多规则或替换为 Semgrep。
    """

    _SQL_START = re.compile(
        r"^\s*(?:SELECT|INSERT|UPDATE|DELETE|REPLACE|WITH|CREATE|ALTER|DROP|TRUNCATE)\b",
        re.IGNORECASE,
    )
    _HTTP_METHODS = {"get", "post", "put", "delete", "patch", "request", "head", "options"}

    def analyze(self, project_path: str) -> list[Finding]:
        root = Path(project_path)
        if not root.exists():
            raise FileNotFoundError(f"代码路径不存在: {project_path}")

        if root.is_file():
            files = [root]
        else:
            ignored_dirs = {".git", ".venv", "venv", "__pycache__", "node_modules"}
            files = sorted(
                path
                for path in root.rglob("*.py")
                if not any(part in ignored_dirs for part in path.parts)
            )

        findings: list[Finding] = []
        for file_path in files:
            try:
                source = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                source = file_path.read_text(encoding="utf-8", errors="replace")
            findings.extend(self.analyze_source(source, str(file_path)))
        return findings

    def analyze_source(self, source: str, file_path: str = "<input>") -> list[Finding]:
        try:
            tree = ast.parse(source, filename=file_path)
        except SyntaxError as exc:
            return [
                Finding(
                    file_path=file_path,
                    line=exc.lineno or 1,
                    column=exc.offset or 0,
                    rule_id="PY-SYNTAX",
                    message=f"语法错误: {exc.msg}",
                    severity="HIGH",
                )
            ]

        findings: list[Finding] = []
        requests_modules, session_constructors, sessions = self._requests_bindings(tree)
        for node in ast.walk(tree):
            findings.extend(self._check_call(node, file_path))
            findings.extend(self._check_sql_call(node, file_path))
            findings.extend(
                self._check_tls_call(
                    node, file_path, requests_modules, session_constructors, sessions
                )
            )
            findings.extend(self._check_hardcoded_secret(node, file_path))
        return findings

    def _check_sql_call(self, node: ast.AST, file_path: str) -> list[Finding]:
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            return []
        if node.func.attr not in {"execute", "executemany"} or not node.args:
            return []

        query = node.args[0]
        if isinstance(query, ast.JoinedStr):
            dynamic = any(isinstance(part, ast.FormattedValue) for part in query.values)
        elif isinstance(query, ast.BinOp) and isinstance(query.op, ast.Add):
            dynamic = any(
                not isinstance(part, ast.Constant) or not isinstance(part.value, str)
                for part in self._add_parts(query)
            )
        else:
            return []

        if not dynamic or not self._SQL_START.match(self._literal_prefix(query)):
            return []
        return [
            Finding(
                file_path=file_path,
                line=node.lineno,
                column=node.col_offset,
                rule_id="PY-SQL-001",
                message="SQL 查询直接拼接动态内容，建议使用参数化查询",
                severity="HIGH",
            )
        ]

    @staticmethod
    def _add_parts(node: ast.AST) -> list[ast.AST]:
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return PythonAnalyzer._add_parts(node.left) + PythonAnalyzer._add_parts(node.right)
        return [node]

    @classmethod
    def _literal_prefix(cls, node: ast.AST) -> str:
        parts = cls._add_parts(node)
        prefix = ""
        for part in parts:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                prefix += part.value
            elif isinstance(part, ast.JoinedStr):
                for item in part.values:
                    if not isinstance(item, ast.Constant) or not isinstance(item.value, str):
                        return prefix
                    prefix += item.value
            else:
                return prefix
        return prefix

    @staticmethod
    def _requests_bindings(tree: ast.AST) -> tuple[set[str], set[str], set[str]]:
        modules: set[str] = set()
        constructors: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(
                    alias.asname or "requests"
                    for alias in node.names
                    if alias.name == "requests"
                )
            elif isinstance(node, ast.ImportFrom) and node.module == "requests":
                constructors.update(
                    alias.asname or "Session"
                    for alias in node.names
                    if alias.name == "Session"
                )

        # Any other binding could shadow an import. In uncertain cases, skip the rule.
        rebound: set[str] = set()
        stores: dict[str, int] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                stores[node.id] = stores.get(node.id, 0) + 1
                rebound.add(node.id)
            elif isinstance(node, ast.arg):
                rebound.add(node.arg)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                rebound.add(node.name)
            elif isinstance(node, ast.ExceptHandler) and node.name:
                rebound.add(node.name)
        modules.difference_update(rebound)
        constructors.difference_update(rebound)

        def is_session_constructor(call: ast.AST) -> bool:
            if not isinstance(call, ast.Call):
                return False
            func = call.func
            return (
                isinstance(func, ast.Attribute)
                and func.attr == "Session"
                and isinstance(func.value, ast.Name)
                and func.value.id in modules
            ) or isinstance(func, ast.Name) and func.id in constructors

        sessions: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target, value = node.targets[0], node.value
            elif isinstance(node, ast.AnnAssign):
                target, value = node.target, node.value
            else:
                continue
            if (
                isinstance(target, ast.Name)
                and stores.get(target.id) == 1
                and is_session_constructor(value)
            ):
                sessions.add(target.id)
        return modules, constructors, sessions

    def _check_tls_call(
        self,
        node: ast.AST,
        file_path: str,
        requests_modules: set[str],
        session_constructors: set[str],
        sessions: set[str],
    ) -> list[Finding]:
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            return []
        if node.func.attr not in self._HTTP_METHODS or not any(
            keyword.arg == "verify"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is False
            for keyword in node.keywords
        ):
            return []

        receiver = node.func.value
        direct_module = isinstance(receiver, ast.Name) and receiver.id in requests_modules
        known_session = isinstance(receiver, ast.Name) and receiver.id in sessions
        inline_session = isinstance(receiver, ast.Call) and (
            isinstance(receiver.func, ast.Attribute)
            and receiver.func.attr == "Session"
            and isinstance(receiver.func.value, ast.Name)
            and receiver.func.value.id in requests_modules
            or isinstance(receiver.func, ast.Name)
            and receiver.func.id in session_constructors
        )
        if not (direct_module or known_session or inline_session):
            return []
        return [
            Finding(
                file_path=file_path,
                line=node.lineno,
                column=node.col_offset,
                rule_id="PY-TLS-001",
                message="HTTP 请求禁用 TLS 证书验证，可能遭受中间人攻击",
                severity="MEDIUM",
            )
        ]

    def _check_call(self, node: ast.AST, file_path: str) -> list[Finding]:
        if not isinstance(node, ast.Call):
            return []

        name = self._call_name(node.func)
        line = getattr(node, "lineno", 1)
        column = getattr(node, "col_offset", 0)

        if name in {"eval", "exec"}:
            return [
                Finding(
                    file_path=file_path,
                    line=line,
                    column=column,
                    rule_id="PY-EVAL-001",
                    message=f"禁止直接使用 {name} 执行动态代码，可能导致代码注入",
                    severity="HIGH",
                )
            ]

        if name == "os.system":
            return [
                Finding(
                    file_path=file_path,
                    line=line,
                    column=column,
                    rule_id="PY-CMD-001",
                    message="使用 os.system 执行系统命令，建议改用参数化的 subprocess 调用",
                    severity="HIGH",
                )
            ]

        if name in {"subprocess.run", "subprocess.call", "subprocess.Popen", "subprocess.check_call"}:
            shell_true = any(
                keyword.arg == "shell"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
                for keyword in node.keywords
            )
            if shell_true:
                return [
                    Finding(
                        file_path=file_path,
                        line=line,
                        column=column,
                        rule_id="PY-CMD-002",
                        message="subprocess 使用 shell=True，可能导致命令注入",
                        severity="HIGH",
                    )
                ]

        if name == "pickle.loads":
            return [
                Finding(
                    file_path=file_path,
                    line=line,
                    column=column,
                    rule_id="PY-DESERIALIZE-001",
                    message="pickle.loads 反序列化不可信数据可能导致任意代码执行",
                    severity="HIGH",
                )
            ]

        if name == "yaml.load" and not any(keyword.arg == "Loader" for keyword in node.keywords):
            return [
                Finding(
                    file_path=file_path,
                    line=line,
                    column=column,
                    rule_id="PY-DESERIALIZE-002",
                    message="yaml.load 未显式指定安全 Loader，建议使用 yaml.safe_load",
                    severity="MEDIUM",
                )
            ]

        return []

    def _check_hardcoded_secret(self, node: ast.AST, file_path: str) -> list[Finding]:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            return []

        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        value = node.value
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            return []

        for target in targets:
            if isinstance(target, ast.Name) and self._looks_like_secret(target.id):
                return [
                    Finding(
                        file_path=file_path,
                        line=getattr(node, "lineno", 1),
                        column=getattr(node, "col_offset", 0),
                        rule_id="PY-SECRET-001",
                        message=f"变量 {target.id} 可能包含硬编码敏感信息",
                        severity="MEDIUM",
                    )
                ]
        return []

    @staticmethod
    def _call_name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = PythonAnalyzer._call_name(node.value)
            return f"{parent}.{node.attr}" if parent else node.attr
        return ""

    @staticmethod
    def _looks_like_secret(name: str) -> bool:
        normalized = name.lower()
        keywords = ("password", "passwd", "secret", "api_key", "apikey", "token")
        return any(keyword in normalized for keyword in keywords)

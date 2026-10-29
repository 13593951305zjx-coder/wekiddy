"""只解析源码的 Python 结构知识图谱；不执行导入，不声称实现完整 CPG。"""

import ast
import hashlib
import io
import posixpath
import tokenize
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from app.knowledge.schemas import CodeGraphRequest, CodeGraphResponse, GraphEdge, GraphNode, SourceFile


MAX_SOURCE_BYTES = 3_000_000
MAX_ARCHIVE_BYTES = 10_000_000
MAX_NODES = 2500
MAX_EDGES = 10_000
IGNORED = {".git", ".venv", "venv", "env", "__pycache__", "node_modules", "site-packages", "__MACOSX"}


def normalized_path(path: str) -> str:
    path = path.replace("\\", "/")
    parts = PurePosixPath(path).parts
    if path.startswith("/") or ":" in path or ".." in parts or "\x00" in path:
        raise ValueError("请提供项目内相对路径，不能包含上级目录或盘符。")
    normalized = posixpath.normpath(path)
    if normalized in {".", ""}:
        raise ValueError("文件路径不能为空。")
    return normalized


def read_python_archive(data: bytes) -> tuple[list[SourceFile], list[str]]:
    """从 ZIP 内存读取 Python 文本，不解压到文件系统。"""
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ValueError("ZIP 不能超过 10 MB。")
    files: list[SourceFile] = []
    warnings: list[str] = []
    total = 0
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if len(archive.infolist()) > 6000:
                raise ValueError("ZIP 条目过多，请排除依赖和构建目录。")
            for entry in archive.infolist():
                path = normalized_path(entry.filename)
                if entry.is_dir() or any(part in IGNORED for part in PurePosixPath(path).parts):
                    continue
                if not path.lower().endswith(".py"):
                    continue
                if entry.file_size > 512_000 or total + entry.file_size > MAX_SOURCE_BYTES:
                    raise ValueError("单个 Python 文件不能超过 512 KB，源码合计不能超过 3 MB。")
                if len(files) >= 150:
                    raise ValueError("一次最多分析 150 个 Python 文件。")
                if entry.flag_bits & 1:
                    raise ValueError("暂不支持加密 ZIP，请使用普通 ZIP。")
                with archive.open(entry) as stream:
                    raw = stream.read(512_001)
                total += len(raw)
                if len(raw) > 512_000 or total > MAX_SOURCE_BYTES:
                    raise ValueError("ZIP 内源码大小超过限制。")
                try:
                    encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
                    code = raw.decode(encoding)
                except (SyntaxError, UnicodeError, LookupError):
                    warnings.append(f"{path}：无法按声明编码读取，已跳过。")
                    continue
                files.append(SourceFile(path=path, code=code))
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError, EOFError) as exc:
        raise ValueError("无法读取 ZIP，请确认文件完整且采用常见 ZIP 压缩格式。") from exc
    if not files:
        raise ValueError("没有找到可读取的 .py 文件。")
    return files, warnings


@dataclass
class Scope:
    node: GraphNode
    tree: ast.AST
    parent: "Scope | None" = None
    bindings: dict[str, tuple[str, str]] = field(default_factory=dict)
    assignments: dict[str, list[ast.expr]] = field(default_factory=dict)
    globals: set[str] = field(default_factory=set)
    nonlocals: set[str] = field(default_factory=set)
    fields: dict[str, list[tuple[ast.expr, "Scope"]]] = field(default_factory=dict)


def text(node: ast.AST | None) -> str:
    return ast.unparse(node) if node is not None else ""


class KnowledgeGraphBuilder:
    def __init__(self):
        self.nodes: dict[str, GraphNode] = {}
        self.edges: dict[tuple[str, str, str, str], GraphEdge] = {}
        self.scopes: dict[str, Scope] = {}
        self.ast_scopes: dict[int, Scope] = {}
        self.modules: dict[str, Scope] = {}
        self.warnings: list[str] = []

    def build(self, payload: CodeGraphRequest) -> CodeGraphResponse:
        # 每个请求独立使用 builder，避免不同项目的符号互相污染。
        files = []
        seen = set()
        total = 0
        for item in payload.files:
            path = normalized_path(item.path)
            if any(part in IGNORED for part in PurePosixPath(path).parts) or not path.lower().endswith(".py"):
                continue
            if path in seen:
                raise ValueError(f"文件路径重复：{path}")
            seen.add(path)
            total += len(item.code.encode("utf-8"))
            if total > MAX_SOURCE_BYTES or len(item.code.encode("utf-8")) > 512_000:
                raise ValueError("单文件最多 512 KB，源码合计最多 3 MB。")
            files.append(SourceFile(path=path, code=item.code))
        if not files:
            raise ValueError("请导入至少一个 Python 文件。")
        for item in sorted(files, key=lambda f: f.path):
            module = item.path[:-3].replace("/", ".")
            if module.endswith(".__init__"):
                module = module[:-9]
            elif module == "__init__":
                module = "<root>"
            node = GraphNode(id=f"file:{item.path}", kind="file", name=item.path,
                             qualified_name=module, file_path=item.path,
                             end_line=max(1, len(item.code.splitlines())), source=item.code,
                             summary="Python 源文件；包含的定义与导入关系见下方。")
            self.add_node(node)
            try:
                tree = ast.parse(item.code, filename=item.path)
            except (SyntaxError, ValueError, RecursionError) as exc:
                self.warnings.append(f"{item.path}：解析失败（{getattr(exc, 'msg', str(exc))}），未建立该文件的内部关系。")
                continue
            scope = Scope(node, tree)
            self.modules[module] = scope
            self.scopes[node.id] = scope
            self.ast_scopes[id(tree)] = scope
            Collector(self, scope).visit(tree)
        for scope in list(self.scopes.values()):
            Calls(self, scope).visit_scope()
            if scope.node.kind == "class":
                for base in scope.tree.bases:
                    bound = self.resolve_expr(base, scope.parent)
                    if bound and bound[0] == "symbol" and self.nodes[bound[1]].kind == "class":
                        self.add_edge(scope.node.id, bound[1], "inherits", "继承", getattr(base, "lineno", 1))
        funcs = [n for n in self.nodes.values() if n.kind == "function"]
        classes = [n for n in self.nodes.values() if n.kind == "class"]
        call_count = sum(e.kind == "calls" and e.resolution != "unresolved" for e in self.edges.values())
        unresolved = sum(len(e.lines) for e in self.edges.values() if e.kind == "calls" and e.resolution == "unresolved")
        overview = f"共读取 {len(files)} 个 Python 文件，识别 {len(funcs)} 个函数/方法、{len(classes)} 个类和 {call_count} 组项目内调用关系。"
        if unresolved:
            overview += f"另有 {unresolved} 处调用属于外部库或暂时无法静态解析，可在图谱中选择显示。"
        return CodeGraphResponse(nodes=list(self.nodes.values()), edges=list(self.edges.values()),
                                 file_count=len(files), function_count=len(funcs), class_count=len(classes),
                                 unresolved_call_count=unresolved, overview=overview,
                                 warnings=self.warnings, files=files)

    def add_node(self, node: GraphNode):
        if len(self.nodes) >= MAX_NODES:
            raise ValueError("图谱超过 2500 个节点，请缩小到一个业务子目录。")
        self.nodes[node.id] = node

    def add_edge(self, source, target, kind, label, line, resolution="resolved"):
        key = (source, target, kind, resolution)
        if key not in self.edges:
            if len(self.edges) >= MAX_EDGES:
                raise ValueError("关系超过 10000 条，请缩小分析范围。")
            digest = hashlib.sha256(repr(key).encode()).hexdigest()[:18]
            self.edges[key] = GraphEdge(id=digest, source=source, target=target, kind=kind,
                                        label=label, resolution=resolution)
        if line not in self.edges[key].lines:
            self.edges[key].lines.append(line)

    def module_scope(self, scope):
        while scope and scope.parent:
            scope = scope.parent
        return scope

    def find_module(self, name):
        if name in self.modules:
            return self.modules[name]
        matches = [s for key, s in self.modules.items() if key.endswith("." + name)]
        return matches[0] if len(matches) == 1 else None

    def resolve_ref(self, reference, depth=0):
        if depth > 10:
            return None
        module = self.find_module(reference)
        if module:
            return ("module", module.node.id)
        parts = reference.split(".")
        for index in range(len(parts) - 1, 0, -1):
            module = self.find_module(".".join(parts[:index]))
            if not module:
                continue
            bound = ("module", module.node.id)
            for attribute in parts[index:]:
                bound = self.attribute(bound, attribute, depth + 1)
                if not bound:
                    break
            if bound:
                return bound
        return None

    def resolve_binding(self, value, scope, depth):
        if not value or depth > 10 or value[0] == "unknown":
            return None
        if value[0] == "ref":
            return self.resolve_ref(value[1], depth + 1) or value
        if value[0] == "assigned":
            assignments = scope.assignments.get(value[1], [])
            if len(assignments) != 1:
                return None
            expression = assignments[0]
            if isinstance(expression, ast.Call):
                target = self.resolve_expr(expression.func, scope, depth + 1)
                if target and target[0] == "symbol" and self.nodes[target[1]].kind == "class":
                    return ("instance", target[1])
            return None
        return value

    def name(self, name, scope, depth=0):
        current = scope
        while current:
            if name in current.globals and current.parent:
                current = self.module_scope(current)
            if name in current.bindings and name not in current.nonlocals:
                return self.resolve_binding(current.bindings[name], current, depth + 1)
            current = current.parent
            # 函数不能通过裸名称访问外层类的属性。
            while current and current.node.kind == "class":
                current = current.parent
        return None

    def attribute(self, owner, attribute, depth=0):
        if not owner or depth > 10:
            return None
        kind, identifier = owner
        if kind == "ref":
            ref = f"{identifier}.{attribute}"
            return self.resolve_ref(ref, depth + 1) or ("ref", ref)
        if kind == "module":
            scope = self.scopes[identifier]
            value = scope.bindings.get(attribute)
            if value:
                return self.resolve_binding(value, scope, depth + 1)
            return self.resolve_ref(f"{scope.node.qualified_name}.{attribute}", depth + 1)
        if kind in {"instance", "symbol"} and identifier in self.scopes:
            scope = self.scopes[identifier]
            value = scope.bindings.get(attribute)
            if value:
                return self.resolve_binding(value, scope, depth + 1)
            assignments = scope.fields.get(attribute, [])
            if kind == "instance" and len(assignments) == 1:
                expression, assignment_scope = assignments[0]
                if isinstance(expression, ast.Call):
                    target = self.resolve_expr(expression.func, assignment_scope, depth + 1)
                    if target and target[0] == "symbol" and self.nodes[target[1]].kind == "class":
                        return ("instance", target[1])
        return None

    def resolve_expr(self, expression, scope, depth=0):
        if depth > 10 or scope is None:
            return None
        if isinstance(expression, ast.Name):
            return self.name(expression.id, scope, depth + 1)
        if isinstance(expression, ast.Attribute):
            return self.attribute(self.resolve_expr(expression.value, scope, depth + 1), expression.attr, depth + 1)
        if isinstance(expression, ast.Call):
            target = self.resolve_expr(expression.func, scope, depth + 1)
            if target and target[0] == "symbol" and self.nodes[target[1]].kind == "class":
                return ("instance", target[1])
        return None


class Collector(ast.NodeVisitor):
    def __init__(self, graph, scope):
        self.graph = graph
        self.scope = scope
        self.local_writes = Counter()

    def bind(self, name, value):
        self.local_writes[name] += 1
        self.scope.bindings[name] = value if self.local_writes[name] == 1 else ("unknown", "")

    def definition(self, node, kind):
        parent = self.scope.node
        qual = f"{parent.qualified_name}.{node.name}"
        identifier = f"{parent.file_path}::{qual}:{node.lineno}"
        source_lines = self.graph.module_scope(self.scope).node.source.splitlines()
        start = min([node.lineno] + [d.lineno for d in node.decorator_list])
        parameters = []
        returns = ""
        signature = node.name
        if kind == "function":
            parameters = [arg.arg for arg in node.args.posonlyargs + node.args.args + node.args.kwonlyargs]
            if node.args.vararg:
                parameters.append("*" + node.args.vararg.arg)
            if node.args.kwarg:
                parameters.append("**" + node.args.kwarg.arg)
            returns = text(node.returns)
            signature = f"{'async ' if isinstance(node, ast.AsyncFunctionDef) else ''}def {node.name}({text(node.args)})"
            if returns:
                signature += f" -> {returns}"
        else:
            signature = f"class {node.name}({', '.join(text(b) for b in node.bases)})"
        doc = ast.get_docstring(node) or ""
        summary = doc.split("\n\n")[0][:1500] if doc else self.describe(node, kind)
        item = GraphNode(id=identifier, kind=kind, name=node.name, qualified_name=qual,
                         file_path=parent.file_path, line=node.lineno, end_line=node.end_lineno,
                         signature=signature, parameters=parameters, returns=returns,
                         docstring=doc[:6000], summary=summary,
                         summary_source="docstring" if doc else "static",
                         source="\n".join(source_lines[start - 1:node.end_lineno]),
                         is_async=isinstance(node, ast.AsyncFunctionDef))
        self.graph.add_node(item)
        self.graph.add_edge(parent.id, item.id, "contains", "包含", node.lineno)
        self.bind(node.name, ("symbol", item.id))
        child = Scope(item, node, self.scope)
        self.graph.scopes[item.id] = child
        self.graph.ast_scopes[id(node)] = child
        if kind == "function":
            for parameter in parameters:
                child.bindings[parameter.lstrip("*")] = ("unknown", "")
            if self.scope.node.kind == "class" and node.args.args:
                first = node.args.args[0].arg
                decorators = {text(d) for d in node.decorator_list}
                if "staticmethod" not in decorators:
                    child.bindings[first] = ("symbol" if "classmethod" in decorators else "instance", parent.id)
        visitor = Collector(self.graph, child)
        visitor.local_writes.update(child.bindings.keys())
        for statement in node.body:
            visitor.visit(statement)

    @staticmethod
    def describe(node, kind):
        if kind == "class":
            methods = [s.name for s in node.body if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))]
            return "定义一个类" + (f"，组织 {len(methods)} 个方法：{'、'.join(methods[:5])}。" if methods else "。")
        operations = []

        def owned(n):
            for child in ast.iter_child_nodes(n):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                    continue
                yield child
                yield from owned(child)

        body = list(owned(node))
        calls = list(dict.fromkeys(text(n.func) for n in body if isinstance(n, ast.Call)))
        values = list(dict.fromkeys(text(n.value) for n in body if isinstance(n, ast.Return) and n.value))
        if calls:
            operations.append("调用 " + "、".join(calls[:5]))
        if any(isinstance(n, (ast.For, ast.While, ast.AsyncFor, ast.comprehension)) for n in body):
            operations.append("包含循环或推导式处理")
        if any(isinstance(n, (ast.If, ast.IfExp, ast.Match)) for n in body):
            operations.append("包含条件分支")
        if values:
            operations.append("返回 " + "；".join(v[:120] for v in values[:2]))
        return "；".join(operations) + "。" if operations else "定义函数；仅凭结构无法确认具体业务用途，可使用 Codex 补充说明。"

    def visit_FunctionDef(self, node):
        self.definition(node, "function")

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        self.definition(node, "class")

    def visit_Import(self, node):
        for alias in node.names:
            self.bind(alias.asname or alias.name.split(".")[0], ("ref", alias.name if alias.asname else alias.name.split(".")[0]))

    def visit_ImportFrom(self, node):
        module = node.module or ""
        if node.level:
            root = self.graph.module_scope(self.scope).node
            package = root.qualified_name.split(".")
            if not root.file_path.endswith("__init__.py"):
                package = package[:-1]
            package = package[:len(package) - node.level + 1] if node.level <= len(package) else []
            module = ".".join(package + ([module] if module else []))
        for alias in node.names:
            if alias.name == "*":
                self.graph.warnings.append(f"{self.scope.node.file_path}:{node.lineno} 使用星号导入，相关调用可能无法解析。")
                continue
            self.bind(alias.asname or alias.name, ("ref", ".".join(filter(None, [module, alias.name]))))

    def visit_Name(self, node):
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.bind(node.id, ("unknown", ""))

    def visit_Assign(self, node):
        self.visit(node.value)
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.bind(target.id, ("assigned", target.id))
                self.scope.assignments.setdefault(target.id, []).append(node.value)
            else:
                self.record_field(target, node.value)
                self.visit(target)

    def visit_AnnAssign(self, node):
        if isinstance(node.target, ast.Name) and node.value is not None:
            self.bind(node.target.id, ("assigned", node.target.id))
            self.scope.assignments.setdefault(node.target.id, []).append(node.value)
        else:
            if node.value is not None:
                self.record_field(node.target, node.value)
            self.visit(node.target)

    def record_field(self, target, value):
        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
            bound = self.scope.bindings.get(target.value.id)
            if bound and bound[0] == "instance":
                self.graph.scopes[bound[1]].fields.setdefault(target.attr, []).append((value, self.scope))

    def visit_Global(self, node):
        self.scope.globals.update(node.names)

    def visit_Nonlocal(self, node):
        self.scope.nonlocals.update(node.names)

    def visit_Lambda(self, node):
        pass


class Calls(ast.NodeVisitor):
    def __init__(self, graph, scope):
        self.graph = graph
        self.scope = scope

    def visit_scope(self):
        for node in self.scope.tree.body:
            self.visit(node)

    def visit_Call(self, node):
        bound = self.graph.resolve_expr(node.func, self.scope)
        target = bound[1] if bound and bound[0] == "symbol" else None
        receiver = self.graph.resolve_expr(node.func.value, self.scope) if isinstance(node.func, ast.Attribute) else None
        resolution = "inferred" if receiver and receiver[0] == "instance" else "resolved"
        label = "调用"
        if target and self.graph.nodes[target].kind not in {"class", "function"}:
            target = None
        if target and self.graph.nodes[target].kind == "class":
            label = "创建实例"
        if not target:
            name = text(node.func)[:180]
            qual = bound[1] if bound and bound[0] == "ref" else name
            digest = hashlib.sha256(f"{self.scope.node.file_path}:{qual}".encode()).hexdigest()[:18]
            target = "external:" + digest
            if target not in self.graph.nodes:
                self.graph.add_node(GraphNode(id=target, kind="external", name=name, qualified_name=qual,
                                               file_path=self.scope.node.file_path, line=node.lineno,
                                               summary="外部库、内置函数或暂时无法确定目标的动态调用；不代表已确认项目内关联。"))
            resolution = "unresolved"
            label = "外部/未解析调用"
        self.graph.add_edge(self.scope.node.id, target, "calls", label, node.lineno, resolution)
        self.generic_visit(node)

    def import_edge(self, reference, line):
        bound = self.graph.resolve_ref(reference)
        if bound and bound[0] in {"symbol", "module"}:
            target_scope = self.graph.module_scope(self.graph.scopes[bound[1]])
            root = self.graph.module_scope(self.scope)
            if target_scope != root:
                self.graph.add_edge(root.node.id, target_scope.node.id, "imports", "导入", line)

    def visit_Import(self, node):
        for alias in node.names:
            self.import_edge(alias.name, node.lineno)

    def visit_ImportFrom(self, node):
        # 使用收集阶段解析过的绑定，兼容相对导入和 __init__ 重导出。
        for alias in node.names:
            value = self.scope.bindings.get(alias.asname or alias.name)
            if value and value[0] == "ref":
                self.import_edge(value[1], node.lineno)

    def visit_FunctionDef(self, node):
        # 默认参数和装饰器在定义函数的外层执行。
        for expression in node.decorator_list + node.args.defaults + [d for d in node.args.kw_defaults if d is not None]:
            self.visit(expression)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        for expression in node.decorator_list + node.bases:
            self.visit(expression)

    def visit_Lambda(self, node):
        pass

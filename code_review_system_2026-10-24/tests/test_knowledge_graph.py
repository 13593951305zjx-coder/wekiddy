import io
import zipfile

import pytest

from app.knowledge.graph import KnowledgeGraphBuilder, read_python_archive
from app.knowledge.schemas import CodeGraphRequest, GraphExplainRequest, SourceFile
from app.knowledge.service import KnowledgeExplanationService


def build(files):
    return KnowledgeGraphBuilder().build(CodeGraphRequest(files=[SourceFile(path=p, code=c) for p, c in files.items()]))


def relations(graph, kind="calls"):
    names = {n.id: n.qualified_name for n in graph.nodes}
    return {(names[e.source], names[e.target]) for e in graph.edges if e.kind == kind and e.resolution != "unresolved"}


def test_cross_file_aliases_relative_import_and_reexport():
    graph = build({
        "demo/api.py": "from .services import fetch as read\ndef endpoint():\n    return read()\n",
        "demo/services/__init__.py": "from .repo import fetch\n",
        "demo/services/repo.py": "def fetch():\n    return [1, 2]\n",
    })
    assert ("demo.api.endpoint", "demo.services.repo.fetch") in relations(graph)
    assert graph.function_count == 2
    assert ("demo.api", "demo.services.repo") in relations(graph, "imports")


def test_forward_calls_and_scope_distinguish_same_function_names():
    graph = build({"main.py": "def first():\n    helper()\n    def helper():\n        return 1\ndef second():\n    helper()\ndef helper():\n    return 2\n"})
    assert ("main.first", "main.first.helper") in relations(graph)
    assert ("main.second", "main.helper") in relations(graph)
    assert ("main.first", "main.helper") not in relations(graph)


def test_class_instance_method_async_and_inheritance():
    graph = build({"main.py": "class Base:\n    pass\nclass Repo(Base):\n    def get(self):\n        return 1\n    async def fetch(self):\n        return self.get()\ndef run():\n    repo = Repo()\n    return repo.get()\n"})
    assert ("main.run", "main.Repo.get") in relations(graph)
    assert ("main.Repo.fetch", "main.Repo.get") in relations(graph)
    assert ("main.Repo", "main.Base") in relations(graph, "inherits")
    fetch = next(n for n in graph.nodes if n.name == "fetch")
    assert fetch.is_async and fetch.line == 6
    assert any(e.resolution == "inferred" for e in graph.edges)


def test_shadowed_import_and_ambiguous_module_do_not_make_false_edges():
    graph = build({
        "main.py": "from tools import helper\ndef run(helper):\n    helper()\ndef other():\n    unknown.helper()\n",
        "a/tools.py": "def helper():\n    pass\n",
        "b/tools.py": "def helper():\n    pass\n",
    })
    assert not relations(graph)
    assert graph.unresolved_call_count == 2


def test_reassigning_parameter_or_class_instance_is_conservative():
    graph = build({"main.py": "class Repo:\n    def get(self):\n        pass\ndef run(value):\n    value = Repo()\n    value = other\n    return value.get()\n"})
    assert ("main.run", "main.Repo.get") not in relations(graph)


def test_imported_service_instance_field_is_inferred_but_reassignment_is_not():
    graph = build({
        "repo.py": "class Repo:\n    def get(self):\n        return 1\n",
        "service.py": "from repo import Repo\nclass Service:\n    def __init__(self):\n        self.repo = Repo()\n    def run(self):\n        return self.repo.get()\n",
    })
    assert ("service.Service.run", "repo.Repo.get") in relations(graph)
    ambiguous = build({"main.py": "class Repo:\n    def get(self): pass\nclass Service:\n    def __init__(self):\n        self.repo = Repo()\n        self.repo = other\n    def run(self):\n        return self.repo.get()\n"})
    assert ("main.Service.run", "main.Repo.get") not in relations(ambiguous)


def test_syntax_errors_are_partial_and_uploaded_code_is_not_executed(tmp_path):
    marker = tmp_path / "must-not-exist"
    graph = build({"safe.py": f"open({str(marker)!r}, 'w').write('bad')\ndef useful():\n    return 1\n", "broken.py": "def broken(:"})
    assert not marker.exists()
    assert graph.function_count == 1
    assert graph.warnings and "broken.py" in graph.warnings[0]


def test_docstring_source_locations_signatures_and_repeated_call_lines():
    graph = build({"main.py": 'def helper():\n    """转换输入数据。"""\n    return 1\ndef run(value: int = 3, *, flag=True) -> int:\n    helper()\n    return helper()\n'})
    helper = next(n for n in graph.nodes if n.name == "helper")
    run = next(n for n in graph.nodes if n.name == "run")
    assert helper.summary_source == "docstring" and "转换" in helper.summary
    assert run.parameters == ["value", "flag"] and run.returns == "int"
    edge = next(e for e in graph.edges if e.source == run.id and e.target == helper.id)
    assert edge.lines == [5, 6]


def zip_bytes(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, code in entries.items():
            archive.writestr(path, code)
    return stream.getvalue()


def test_archive_reads_python_encoding_and_skips_dependencies():
    files, warnings = read_python_archive(zip_bytes({
        "demo/main.py": b"# coding: latin-1\n# caf\xe9\ndef run(): pass\n",
        "demo/.venv/huge.py": "broken(:",
        "demo/readme.md": "readme",
    }))
    assert len(files) == 1 and "café" in files[0].code and not warnings


def test_archive_rejects_traversal_oversize_and_invalid_zip():
    with pytest.raises(ValueError, match="相对路径"):
        read_python_archive(zip_bytes({"../evil.py": "pass"}))
    with pytest.raises(ValueError, match="512 KB"):
        read_python_archive(zip_bytes({"large.py": "#" * 512_001}))
    with pytest.raises(ValueError, match="无法读取 ZIP"):
        read_python_archive(b"not a zip")


def test_duplicate_paths_rejected_and_empty_files_are_supported():
    with pytest.raises(ValueError, match="重复"):
        KnowledgeGraphBuilder().build(CodeGraphRequest(files=[SourceFile(path="a.py", code=""), SourceFile(path="./a.py", code="")]))
    assert build({"empty.py": ""}).file_count == 1


def test_explanation_is_bound_to_real_nodes_and_cannot_change_relations():
    files = [SourceFile(path="demo.py", code="def run(value):\n    return value * 2\n")]
    graph = KnowledgeGraphBuilder().build(CodeGraphRequest(files=files))
    node = next(n for n in graph.nodes if n.kind == "function")

    class Client:
        model = "test-model"

        def run_structured(self, prompt, schema):
            assert "不可信数据" in prompt and "return value * 2" in prompt
            return {"overview": "处理数值", "explanations": [{"id": node.id, "summary": "将输入值翻倍并返回。"}]}

    response = KnowledgeExplanationService(Client()).explain(GraphExplainRequest(files=files, node_ids=[node.id]))
    assert response.explanations[0].id == node.id

    class WrongClient(Client):
        def run_structured(self, *_):
            return {"overview": "wrong", "explanations": [{"id": "invented", "summary": "wrong"}]}

    with pytest.raises(RuntimeError, match="不一致"):
        KnowledgeExplanationService(WrongClient()).explain(GraphExplainRequest(files=files, node_ids=[node.id]))

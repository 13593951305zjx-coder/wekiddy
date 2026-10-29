from typing import Literal

from pydantic import BaseModel, Field


class SourceFile(BaseModel):
    path: str = Field(min_length=1, max_length=400)
    code: str = Field(max_length=512_000)


class CodeGraphRequest(BaseModel):
    files: list[SourceFile] = Field(min_length=1, max_length=150)


class GraphNode(BaseModel):
    id: str
    kind: Literal["file", "class", "function", "external"]
    name: str
    qualified_name: str
    file_path: str
    line: int = 1
    end_line: int = 1
    signature: str = ""
    parameters: list[str] = Field(default_factory=list)
    returns: str = ""
    docstring: str = ""
    summary: str = ""
    summary_source: str = "static"
    source: str = ""
    is_async: bool = False


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    kind: Literal["contains", "imports", "calls", "inherits"]
    label: str
    resolution: Literal["resolved", "inferred", "unresolved"] = "resolved"
    lines: list[int] = Field(default_factory=list)


class CodeGraphResponse(BaseModel):
    analyzer: str = "python-ast-knowledge-graph"
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    file_count: int
    function_count: int
    class_count: int
    unresolved_call_count: int
    overview: str
    warnings: list[str] = Field(default_factory=list)
    files: list[SourceFile]


class GraphExplainRequest(CodeGraphRequest):
    node_ids: list[str] = Field(default_factory=list, max_length=8)


class NodeExplanation(BaseModel):
    id: str
    summary: str = Field(min_length=1, max_length=2500)


class GraphExplainResponse(BaseModel):
    overview: str = Field(max_length=6000)
    explanations: list[NodeExplanation]
    provider: str = "codex"
    model: str = ""

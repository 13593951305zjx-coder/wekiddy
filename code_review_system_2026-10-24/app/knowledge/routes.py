from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.knowledge.graph import MAX_ARCHIVE_BYTES, KnowledgeGraphBuilder, read_python_archive
from app.knowledge.schemas import CodeGraphRequest, CodeGraphResponse, GraphExplainRequest, GraphExplainResponse
from app.knowledge.service import KnowledgeExplanationService


router = APIRouter(prefix="/knowledge", tags=["代码知识图谱"])


@router.post("/graph", response_model=CodeGraphResponse)
def build_graph(payload: CodeGraphRequest):
    try:
        return KnowledgeGraphBuilder().build(payload)
    except (ValueError, RecursionError) as exc:
        raise HTTPException(422, str(exc) if isinstance(exc, ValueError) else "代码嵌套过深，请缩小范围。") from exc


@router.post("/archive", response_model=CodeGraphResponse)
async def build_archive_graph(request: Request):
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_ARCHIVE_BYTES:
            raise HTTPException(413, "ZIP 不能超过 10 MB。")

    def analyze():
        files, warnings = read_python_archive(bytes(data))
        graph = KnowledgeGraphBuilder().build(CodeGraphRequest(files=files))
        graph.warnings = warnings + graph.warnings
        return graph

    try:
        return await run_in_threadpool(analyze)
    except (ValueError, RecursionError) as exc:
        raise HTTPException(422, str(exc) if isinstance(exc, ValueError) else "代码嵌套过深，请缩小范围。") from exc


@router.post("/explain", response_model=GraphExplainResponse)
def explain_graph(payload: GraphExplainRequest):
    try:
        return KnowledgeExplanationService().explain(payload)
    except (ValueError, RecursionError) as exc:
        raise HTTPException(422, str(exc) if isinstance(exc, ValueError) else "代码嵌套过深，请缩小范围。") from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc

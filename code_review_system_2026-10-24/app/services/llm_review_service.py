from typing import Any

from app.llm.client import LLMClient
from app.llm.codex_client import CodexClient
from app.schemas import LLMReviewRequest, LLMReviewResponse


class LLMReviewService:
    """大语言模型代码审查业务服务。"""

    def __init__(
        self,
        client: LLMClient | None = None,
        codex_client: CodexClient | None = None,
    ) -> None:
        self.client = client or LLMClient()
        self.codex_client = codex_client or CodexClient()

    def review(self, payload: LLMReviewRequest) -> LLMReviewResponse:
        if payload.provider == "codex":
            review_client = self.codex_client
            result: dict[str, Any] = review_client.review(
                code=payload.code,
                context=payload.context,
                static_findings=payload.static_findings,
                file_path=payload.file_path,
            )
        else:
            review_client = self.client
            result = review_client.review(
                code=payload.code,
                context=payload.context,
                static_findings=payload.static_findings,
            )
        return LLMReviewResponse(
            provider=payload.provider,
            model=review_client.model or "codex-default",
            result=result,
        )

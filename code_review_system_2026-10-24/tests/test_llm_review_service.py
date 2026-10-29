from app.schemas import LLMReviewRequest
from app.services.llm_review_service import LLMReviewService


class FakeClient:
    model = "fake-model"

    def __init__(self) -> None:
        self.kwargs = None

    def review(self, **kwargs):
        self.kwargs = kwargs
        return {"is_vulnerability": False}


def test_service_routes_codex_reviews_to_codex_client() -> None:
    openai_client = FakeClient()
    codex_client = FakeClient()
    service = LLMReviewService(client=openai_client, codex_client=codex_client)

    response = service.review(
        LLMReviewRequest(provider="codex", file_path="src/main.py", code="print('ok')")
    )

    assert response.provider == "codex"
    assert response.model == "fake-model"
    assert codex_client.kwargs["file_path"] == "src/main.py"
    assert openai_client.kwargs is None

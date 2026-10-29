from app.llm.client import LLMClient


class FakeLLMClient(LLMClient):
    def _chat_completion(self, messages):
        return "```json\n{\"is_vulnerability\": true, \"severity\": \"HIGH\"}\n```"


def test_llm_client_parses_json_response_without_network() -> None:
    result = FakeLLMClient(api_key="test-key").review("eval(user_input)")
    assert result["is_vulnerability"] is True
    assert result["severity"] == "HIGH"


def test_llm_client_requires_api_key() -> None:
    try:
        LLMClient(api_key="").review("print('hello')")
    except RuntimeError as exc:
        assert "LLM_API_KEY" in str(exc)
    else:
        raise AssertionError("未配置 API 密钥时应拒绝调用")

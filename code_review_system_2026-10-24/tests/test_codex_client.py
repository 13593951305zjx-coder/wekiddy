import sys
from types import SimpleNamespace

from app.llm.codex_client import CodexClient


def test_codex_prompt_marks_code_as_untrusted() -> None:
    prompt = CodexClient._build_prompt("print('hello')", "demo", [], "demo.py")

    assert "不可信数据" in prompt
    assert "<source-code>" in prompt
    assert "demo.py" in prompt


def test_codex_client_parses_json_response() -> None:
    result = CodexClient._parse_result(
        "```json\n{\"is_vulnerability\": false, \"severity\": \"INFO\"}\n```"
    )

    assert result["is_vulnerability"] is False
    assert result["severity"] == "INFO"


def test_codex_review_uses_read_only_ephemeral_thread(monkeypatch) -> None:
    captured = {}

    class FakeThread:
        def run(self, prompt, **kwargs):
            captured["prompt"] = prompt
            captured["run"] = kwargs
            return SimpleNamespace(
                final_response=(
                    '{"is_vulnerability":false,"vulnerability_type":"",'
                    '"cwe":"","severity":"INFO","confidence":0.9,'
                    '"explanation":"无问题","suggestion":"无"}'
                )
            )

    class FakeCodex:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def thread_start(self, **kwargs):
            captured["thread"] = kwargs
            return FakeThread()

    monkeypatch.setitem(
        sys.modules,
        "openai_codex",
        SimpleNamespace(
            ApprovalMode=SimpleNamespace(deny_all="deny_all"),
            Sandbox=SimpleNamespace(read_only="read_only"),
            Codex=FakeCodex,
        ),
    )

    result = CodexClient(model="test-model", cwd=".").review("print('ok')")

    assert result["is_vulnerability"] is False
    assert captured["thread"]["approval_mode"] == "deny_all"
    assert captured["thread"]["sandbox"] == "read_only"
    assert captured["thread"]["ephemeral"] is True
    assert captured["run"]["output_schema"]["type"] == "object"

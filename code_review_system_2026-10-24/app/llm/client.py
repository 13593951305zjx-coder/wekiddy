"""OpenAI 兼容接口的大语言模型客户端。"""

import json
import os
import urllib.error
import urllib.request
from typing import Any


DEFAULT_SYSTEM_PROMPT = """你是一名专业的软件安全审查工程师。
请审查用户提供的代码，重点关注注入、命令执行、危险反序列化、敏感信息泄露、权限控制和输入校验问题。
必须只返回一个合法 JSON 对象，不要输出 Markdown 代码块。JSON 字段如下：
{
  \"is_vulnerability\": true,
  \"vulnerability_type\": \"漏洞类型，没有则为空字符串\",
  \"cwe\": \"CWE 编号，没有则为空字符串\",
  \"severity\": \"CRITICAL/HIGH/MEDIUM/LOW/INFO\",
  \"confidence\": 0.0,
  \"explanation\": \"判断依据\",
  \"suggestion\": \"修复建议\"
}
"""


class LLMClient:
    """调用 OpenAI 兼容 Chat Completions 接口。"""

    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 model: str | None = None, timeout: int = 60) -> None:
        self.api_key = api_key or os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY", "")
        self.base_url = (base_url or os.getenv("LLM_BASE_URL")
                         or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.model = model or os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def review(self, code: str, context: str = "",
               static_findings: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if not self.configured:
            raise RuntimeError("未配置 LLM_API_KEY，请先配置大语言模型 API 密钥")
        findings_text = json.dumps(static_findings or [], ensure_ascii=False, indent=2)
        user_prompt = (f"代码上下文：\n{context or '无'}\n\n"
                       f"静态分析结果：\n{findings_text}\n\n"
                       f"待审查代码：\n```\n{code}\n```")
        content = self._chat_completion([
            {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ])
        return self._parse_json_result(content)

    def _chat_completion(self, messages: list[dict[str, str]]) -> str:
        body = json.dumps({"model": self.model, "temperature": 0.1,
                           "messages": messages}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=body,
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"大语言模型接口请求失败（HTTP {exc.code}）：{detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"无法连接大语言模型接口：{exc}") from exc
        try:
            return str(payload["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("大语言模型返回格式不符合 Chat Completions 规范") from exc

    @staticmethod
    def _parse_json_result(content: str) -> dict[str, Any]:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError:
            return {"is_vulnerability": None, "vulnerability_type": "", "cwe": "",
                    "severity": "INFO", "confidence": 0.0,
                    "explanation": "模型未返回合法 JSON，原始结果已保留",
                    "suggestion": "请检查模型提示词或响应格式", "raw_response": content}
        if not isinstance(result, dict):
            raise RuntimeError("大语言模型返回的 JSON 顶层结构必须是对象")
        return result

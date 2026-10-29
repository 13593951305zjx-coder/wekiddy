from __future__ import annotations

import base64
import binascii
import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


class GitHubClientError(RuntimeError):
    """Raised when a GitHub URL or API request cannot be handled."""


@dataclass(frozen=True)
class PullRequestRef:
    owner: str
    repo: str
    number: int


def parse_pull_request_url(value: str) -> PullRequestRef:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in {"github.com", "www.github.com"}:
        raise GitHubClientError("请输入 github.com 的 Pull Request 地址。")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 4 or parts[2].lower() != "pull" or not parts[3].isdigit():
        raise GitHubClientError("Pull Request 地址格式应为 https://github.com/组织/仓库/pull/编号。")
    return PullRequestRef(owner=parts[0], repo=parts[1], number=int(parts[3]))


class GitHubClient:
    """Small GitHub REST client using only the Python standard library."""

    def __init__(self, token: str | None = None, api_base_url: str | None = None, timeout: float = 20.0) -> None:
        self.token = token if token is not None else os.environ.get("GITHUB_TOKEN", "").strip()
        self.api_base_url = (api_base_url or os.environ.get("GITHUB_API_BASE_URL", "https://api.github.com")).rstrip("/")
        self.timeout = timeout

    def _request_json(self, path: str, query: dict[str, str] | None = None) -> object:
        url = f"{self.api_base_url}{path}"
        if query:
            encoded = "&".join(f"{quote(str(key))}={quote(str(value))}" for key, value in query.items())
            url = f"{url}?{encoded}"
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "code-review-system/0.1",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(url, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise GitHubClientError("GitHub 访问被拒绝，请检查 GITHUB_TOKEN 是否有效且具备仓库读取权限。") from exc
            if exc.code == 404:
                raise GitHubClientError("找不到该 Pull Request，或当前 Token 无权访问这个仓库。") from exc
            raise GitHubClientError(f"GitHub API 请求失败（HTTP {exc.code}）。") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise GitHubClientError("无法连接 GitHub API，请检查网络连接或稍后重试。") from exc

    def get_pull_request(self, ref: PullRequestRef) -> dict:
        payload = self._request_json(f"/repos/{quote(ref.owner)}/{quote(ref.repo)}/pulls/{ref.number}")
        if not isinstance(payload, dict):
            raise GitHubClientError("GitHub 返回的 Pull Request 数据格式无效。")
        return payload

    def list_pull_request_files(self, ref: PullRequestRef) -> list[dict]:
        files: list[dict] = []
        for page in range(1, 11):
            payload = self._request_json(
                f"/repos/{quote(ref.owner)}/{quote(ref.repo)}/pulls/{ref.number}/files",
                {"per_page": "100", "page": str(page)},
            )
            if not isinstance(payload, list):
                raise GitHubClientError("GitHub 返回的 Pull Request 文件列表格式无效。")
            files.extend(item for item in payload if isinstance(item, dict))
            if len(payload) < 100:
                break
        return files

    def get_file_at_ref(self, ref: PullRequestRef, path: str, git_ref: str) -> str:
        encoded_path = quote(path, safe="/")
        payload = self._request_json(
            f"/repos/{quote(ref.owner)}/{quote(ref.repo)}/contents/{encoded_path}",
            {"ref": git_ref},
        )
        if not isinstance(payload, dict) or payload.get("encoding") != "base64" or not isinstance(payload.get("content"), str):
            raise GitHubClientError(f"文件 {path} 太大、是二进制文件，或 GitHub 未返回可分析内容。")
        try:
            return base64.b64decode(payload["content"], validate=False).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError) as exc:
            raise GitHubClientError(f"文件 {path} 不是可直接分析的 UTF-8 文本。") from exc


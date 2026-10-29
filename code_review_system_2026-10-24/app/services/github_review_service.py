from __future__ import annotations

from app.analyzers.python_analyzer import PythonAnalyzer
from app.github.client import GitHubClient, GitHubClientError, parse_pull_request_url
from app.llm.codex_client import CodexClient
from app.llm.client import LLMClient
from app.schemas import (
    FindingResponse,
    GitHubPRFileReview,
    GitHubPRReviewRequest,
    GitHubPRReviewResponse,
    LLMReviewRequest,
)
from app.services.llm_review_service import LLMReviewService


class GitHubPRReviewService:
    """读取 GitHub Pull Request，并复用现有静态分析与 LLM 审查能力。"""

    def __init__(
        self,
        client: GitHubClient | None = None,
        analyzer: PythonAnalyzer | None = None,
        llm_service: LLMReviewService | None = None,
    ) -> None:
        self.client = client or GitHubClient()
        self.analyzer = analyzer or PythonAnalyzer()
        self.llm_service = llm_service or LLMReviewService(client=LLMClient(), codex_client=CodexClient())

    def review(self, payload: GitHubPRReviewRequest) -> GitHubPRReviewResponse:
        ref = parse_pull_request_url(payload.pr_url)
        pull_request = self.client.get_pull_request(ref)
        files = self.client.list_pull_request_files(ref)
        head_sha = str((pull_request.get("head") or {}).get("sha") or "")
        if not head_sha:
            raise GitHubClientError("Pull Request 缺少 head commit，无法读取代码。")

        file_reviews: list[GitHubPRFileReview] = []
        analyzed_count = 0
        skipped_count = 0
        for file in files[: payload.max_files]:
            path = str(file.get("filename") or "")
            status = str(file.get("status") or "modified")
            additions = int(file.get("additions") or 0)
            deletions = int(file.get("deletions") or 0)
            if status == "removed" or not path.lower().endswith(".py"):
                skipped_count += 1
                file_reviews.append(
                    GitHubPRFileReview(
                        path=path,
                        status=status,
                        additions=additions,
                        deletions=deletions,
                        analyzed=False,
                        findings=[],
                        skipped_reason="当前版本只对 Python 文件运行静态分析。",
                    )
                )
                continue
            try:
                code = self.client.get_file_at_ref(ref, path, head_sha)
                findings = self.analyzer.analyze_source(code, path)
                finding_models = [FindingResponse(**finding.__dict__) for finding in findings]
                llm_result = None
                llm_error = None
                if payload.include_llm and analyzed_count < payload.max_llm_files:
                    try:
                        llm_response = self.llm_service.review(
                            LLMReviewRequest(
                                provider=payload.provider,
                                file_path=path,
                                code=code,
                                context=f"GitHub Pull Request #{ref.number}: {pull_request.get('title', '')}",
                                static_findings=[finding.model_dump() for finding in finding_models],
                            )
                        )
                        llm_result = llm_response.model_dump()
                    except (RuntimeError, ValueError) as exc:
                        llm_error = str(exc)
                file_reviews.append(
                    GitHubPRFileReview(
                        path=path,
                        status=status,
                        additions=additions,
                        deletions=deletions,
                        analyzed=True,
                        findings=finding_models,
                        llm_review=llm_result,
                        llm_error=llm_error,
                    )
                )
                analyzed_count += 1
            except GitHubClientError as exc:
                skipped_count += 1
                file_reviews.append(
                    GitHubPRFileReview(
                        path=path,
                        status=status,
                        additions=additions,
                        deletions=deletions,
                        analyzed=False,
                        findings=[],
                        skipped_reason=str(exc),
                    )
                )

        finding_count = sum(len(item.findings) for item in file_reviews)
        return GitHubPRReviewResponse(
            pr_url=str(pull_request.get("html_url") or payload.pr_url),
            repository=f"{ref.owner}/{ref.repo}",
            number=ref.number,
            title=str(pull_request.get("title") or ""),
            state=str(pull_request.get("state") or "unknown"),
            head_sha=head_sha,
            base_branch=str((pull_request.get("base") or {}).get("ref") or ""),
            changed_file_count=int(pull_request.get("changed_files") or len(files)),
            analyzed_file_count=analyzed_count,
            skipped_file_count=skipped_count,
            finding_count=finding_count,
            files=file_reviews,
            warnings=(
                [f"本次最多分析 {payload.max_files} 个文件。"] if len(files) > payload.max_files else []
            ) + (["静态分析结果暂未发布到 GitHub PR 评论区。"] if not payload.post_comments else ["当前版本尚未配置自动发布 PR 评论。"]),
        )


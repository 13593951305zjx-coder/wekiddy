"""Persist editor reviews and compare findings with the last parseable version."""

import ast
from collections import defaultdict, deque
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import posixpath
import sqlite3
from uuid import uuid4

from app.schemas import (
    CodeAnalyzeRequest,
    CodeAnalyzeResponse,
    ReviewChange,
    ReviewComparison,
    ReviewHistoryDetail,
    ReviewHistoryItem,
    ReviewHistoryList,
)
from app.services.analysis_service import AnalysisService


class ReviewHistoryService:
    """Keep snapshots locally; submitted source is parsed, never executed."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        default_path = Path(__file__).resolve().parents[2] / "data" / "review_history.sqlite3"
        self.db_path = Path(db_path or os.getenv("CODE_REVIEW_HISTORY_DB") or default_path)
        self.analyzer = AnalysisService()

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("""
            CREATE TABLE IF NOT EXISTS review_history (
                id TEXT PRIMARY KEY,
                path_key TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                analysis_json TEXT NOT NULL,
                parseable INTEGER NOT NULL,
                snapshot_json TEXT NOT NULL
            )
        """)
        connection.execute(
            "CREATE INDEX IF NOT EXISTS review_history_path ON review_history(path_key)"
        )
        return connection

    @staticmethod
    def _path_key(file_path: str) -> str:
        return posixpath.normpath(file_path.strip().replace("\\", "/"))

    def record(self, payload: CodeAnalyzeRequest) -> ReviewHistoryDetail:
        if len(payload.code.encode("utf-8")) > 1_000_000:
            raise ValueError("审查历史单份代码最多保存 1 MB，请缩小文件后重试。")
        analysis = self.analyzer.analyze_python(payload)
        parseable = not any(f.rule_id == "PY-SYNTAX" for f in analysis.findings)
        source_hash = hashlib.sha256(payload.code.encode("utf-8")).hexdigest()
        path_key = self._path_key(payload.file_path)
        analysis_json = analysis.model_dump_json()
        with closing(self._connect()) as connection, connection:
            # Serialize baseline selection and insertion, including across workers.
            connection.execute("BEGIN IMMEDIATE")
            latest = connection.execute(
                "SELECT * FROM review_history WHERE path_key = ? ORDER BY rowid DESC LIMIT 1",
                (path_key,),
            ).fetchone()
            if latest and latest["source_hash"] == source_hash and latest["analysis_json"] == analysis_json:
                return ReviewHistoryDetail.model_validate_json(latest["snapshot_json"])
            baseline_row = connection.execute(
                "SELECT snapshot_json FROM review_history WHERE path_key = ? AND parseable = 1 ORDER BY rowid DESC LIMIT 1",
                (path_key,),
            ).fetchone()
            baseline = (
                ReviewHistoryDetail.model_validate_json(baseline_row["snapshot_json"])
                if baseline_row else None
            )
            comparison = self.compare(payload.code, analysis, baseline)
            snapshot = ReviewHistoryDetail(
                id=str(uuid4()),
                file_path=payload.file_path,
                created_at=datetime.now(timezone.utc),
                finding_count=analysis.finding_count,
                high_risk_count=sum(f.severity.upper() in {"HIGH", "CRITICAL"} for f in analysis.findings),
                line_count=len(payload.code.splitlines()),
                new_count=comparison.new_count if comparison.available else None,
                persistent_count=comparison.persistent_count if comparison.available else None,
                absent_count=comparison.absent_count if comparison.available else None,
                code=payload.code,
                analysis=analysis,
                comparison=comparison,
            )
            connection.execute(
                "INSERT INTO review_history VALUES (?, ?, ?, ?, ?, ?)",
                (snapshot.id, path_key, source_hash, analysis_json, int(parseable), snapshot.model_dump_json()),
            )
            return snapshot

    def list_all(self, file_path: str | None = None, limit: int = 30, offset: int = 0) -> ReviewHistoryList:
        where = " WHERE path_key = ?" if file_path is not None else ""
        params = (self._path_key(file_path),) if file_path is not None else ()
        with closing(self._connect()) as connection:
            total = connection.execute("SELECT COUNT(*) FROM review_history" + where, params).fetchone()[0]
            # Extract only list metadata; source and full results stay in the detail endpoint.
            fields = ", ".join(
                f"json_extract(snapshot_json, '$.{field}') AS {field}"
                for field in ReviewHistoryItem.model_fields
            )
            rows = connection.execute(
                f"SELECT {fields} FROM review_history" + where + " ORDER BY rowid DESC LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()
        return ReviewHistoryList(total=total, items=[ReviewHistoryItem(**dict(row)) for row in rows])

    def get(self, review_id: str) -> ReviewHistoryDetail | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT snapshot_json FROM review_history WHERE id = ?", (review_id,)
            ).fetchone()
        return ReviewHistoryDetail.model_validate_json(row["snapshot_json"]) if row else None

    @staticmethod
    def _fingerprints(code: str, analysis: CodeAnalyzeResponse) -> list[tuple[str, str, str]]:
        tree = ast.parse(code)
        anchors: dict[tuple[int, int], tuple[str, str]] = {}

        def visit(node: ast.AST, scope: tuple[str, ...] = ()) -> None:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                scope += (node.name,)
            if isinstance(node, (ast.Call, ast.Assign, ast.AnnAssign)):
                anchors[(node.lineno, node.col_offset)] = (
                    ".".join(scope), ast.dump(node, include_attributes=False)
                )
            for child in ast.iter_child_nodes(node):
                visit(child, scope)

        visit(tree)
        lines = code.splitlines()
        return [
            (finding.rule_id, *anchors.get(
                (finding.line, finding.column),
                ("", lines[finding.line - 1].strip() if 0 < finding.line <= len(lines) else finding.message),
            ))
            for finding in analysis.findings
        ]

    @classmethod
    def compare(
        cls, code: str, analysis: CodeAnalyzeResponse, baseline: ReviewHistoryDetail | None
    ) -> ReviewComparison:
        if any(f.rule_id == "PY-SYNTAX" for f in analysis.findings):
            return ReviewComparison(explanation="当前代码有语法错误，暂不判断旧问题是否消失；修正语法后会继续与最近可解析的版本对比。")
        if baseline is None:
            return ReviewComparison(explanation="这是该文件的首个可解析版本，已建立基线。修改后再次分析即可看到问题变化。")

        old_keys = cls._fingerprints(baseline.code, baseline.analysis)
        new_keys = cls._fingerprints(code, analysis)
        candidates: dict[tuple[str, str, str], deque[int]] = defaultdict(deque)
        for index, key in enumerate(old_keys):
            candidates[key].append(index)
        matched: set[int] = set()
        changes: list[ReviewChange] = []
        for finding, key in zip(analysis.findings, new_keys):
            status = "new"
            if candidates[key]:
                matched.add(candidates[key].popleft())
                status = "persistent"
            changes.append(ReviewChange(status=status, finding=finding))
        changes.extend(
            ReviewChange(status="absent", finding=finding)
            for index, finding in enumerate(baseline.analysis.findings) if index not in matched
        )
        return ReviewComparison(
            available=True,
            baseline_id=baseline.id,
            baseline_created_at=baseline.created_at,
            new_count=sum(change.status == "new" for change in changes),
            persistent_count=sum(change.status == "persistent" for change in changes),
            absent_count=sum(change.status == "absent" for change in changes),
            explanation="与该文件上一次可解析的分析对比，按规则、函数/类位置和代码结构匹配；仅移动行号不会视为新增问题。未再检出仅表示当前静态规则不再命中。",
            changes=changes,
        )

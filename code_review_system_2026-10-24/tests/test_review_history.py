from concurrent.futures import ThreadPoolExecutor

from app.schemas import CodeAnalyzeRequest
from app.services.review_history_service import ReviewHistoryService


def save(service, code, path="src/demo.py"):
    return service.record(CodeAnalyzeRequest(file_path=path, code=code))


def test_history_survives_new_service_and_list_excludes_source(tmp_path):
    database = tmp_path / "history.sqlite3"
    first = save(ReviewHistoryService(database), "import os\nos.system(command)\n")
    restarted = ReviewHistoryService(database)
    assert restarted.get(first.id).code == first.code
    history = restarted.list_all()
    assert history.total == 1
    assert "code" not in history.items[0].model_dump()
    assert history.items[0].new_count is None


def test_changes_track_new_persistent_and_absent(tmp_path):
    service = ReviewHistoryService(tmp_path / "history.sqlite3")
    first = save(service, "import os\nimport yaml\nos.system(command)\nyaml.load(data)\n")
    second = save(service, "import os\nimport yaml\nos.system(command)\nyaml.safe_load(data)\neval(expression)\n")
    changes = second.comparison
    assert changes.baseline_id == first.id
    assert (changes.new_count, changes.persistent_count, changes.absent_count) == (1, 1, 1)
    assert next(c for c in changes.changes if c.status == "absent").finding.rule_id == "PY-DESERIALIZE-002"


def test_line_moves_and_whitespace_do_not_create_new_findings(tmp_path):
    service = ReviewHistoryService(tmp_path / "history.sqlite3")
    save(service, "import os\ndef process(value):\n    os.system(value)\n")
    second = save(service, "# new header\n\nimport os\n\ndef process(value):\n    os.system( value )\n")
    assert (second.new_count, second.persistent_count, second.absent_count) == (0, 1, 0)


def test_duplicate_calls_are_counted_separately_and_scopes_are_kept(tmp_path):
    service = ReviewHistoryService(tmp_path / "history.sqlite3")
    save(service, "def first(x):\n    eval(x)\n    eval(x)\n")
    one_call = save(service, "def first(x):\n    eval(x)\n")
    assert (one_call.new_count, one_call.persistent_count, one_call.absent_count) == (0, 1, 1)
    moved_scope = save(service, "def second(x):\n    eval(x)\n")
    assert (moved_scope.new_count, moved_scope.persistent_count, moved_scope.absent_count) == (1, 0, 1)


def test_syntax_error_cannot_mark_old_findings_absent(tmp_path):
    service = ReviewHistoryService(tmp_path / "history.sqlite3")
    first = save(service, "eval(expression)\n")
    broken = save(service, "def broken(:\n")
    assert not broken.comparison.available
    assert broken.absent_count is None
    assert broken.comparison.changes == []
    repaired = save(service, "print(expression)\n")
    assert repaired.comparison.baseline_id == first.id
    assert repaired.absent_count == 1


def test_repeated_parallel_requests_do_not_duplicate_versions(tmp_path):
    service = ReviewHistoryService(tmp_path / "history.sqlite3")
    with ThreadPoolExecutor(max_workers=5) as pool:
        snapshots = list(pool.map(lambda _: save(service, "eval(expression)\n"), range(8)))
    assert len({item.id for item in snapshots}) == 1
    assert service.list_all().total == 1


def test_path_filter_and_pagination_do_not_mix_files(tmp_path):
    service = ReviewHistoryService(tmp_path / "history.sqlite3")
    first = save(service, "eval(expression)\n", "src\\demo.py")
    second = save(service, "print(expression)\n", "src/./demo.py")
    other = save(service, "print('other')\n", "other/demo.py")
    assert second.comparison.baseline_id == first.id
    assert other.comparison.baseline_id is None
    page = service.list_all("src/demo.py", limit=1, offset=1)
    assert page.total == 2
    assert [item.id for item in page.items] == [first.id]
    assert service.get("unknown") is None

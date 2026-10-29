#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_all.py - machine-verify the deliberately buggy code corpus.

Checks every entry in manifest.json against the real toolchains:

  * syntax files   : parser/compiler must fail at the documented line with the
                     documented diagnostic substring;
  * runtime files  : the documented case must raise the documented exception at
                     the documented line (uncaught), and the CLI contract must hold;
  * logic files    : the documented case must print exactly the documented
                     (buggy) value, which must differ from the expected value;
  * structure      : file sizes / language / ASCII / no BOM / function counts.

Requirements: Python 3.8+, Node.js (for the JavaScript files), JDK 8+
(for the Java files).  Tools are resolved from PATH; override with environment
variables PYTHON_BIN, NODE_BIN, JAVAC_BIN, JAVA_BIN.

Usage:
    python verify_all.py                     # all languages, skip missing toolchains
    python verify_all.py --strict            # missing toolchain = failure
    python verify_all.py --lang python       # one language only (repeatable)
    python verify_all.py --verbose

Exit code: 0 = every executed check passed, 1 = at least one failure.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "manifest.json"

LANG_PREFIX = {"python": "py", "javascript": "js", "java": "java"}
LANG_LABEL = {"python": "Python", "javascript": "JavaScript", "java": "Java 8"}
THRESHOLDS = {"syntax": 120, "runtime": 200, "logic": 170}

EXPECTED_FILES = {
    "python": [
        "python/syntax_01_missing_colon.py",
        "python/syntax_02_literal_assignment.py",
        "python/runtime_01_service_pipeline.py",
        "python/logic_01_inventory_report.py",
    ],
    "javascript": [
        "javascript/syntax_01_missing_paren.js",
        "javascript/syntax_02_invalid_operator.js",
        "javascript/runtime_01_order_pipeline.js",
        "javascript/logic_01_cart_report.js",
    ],
    "java": [
        "java/Syntax01MissingSemicolon.java",
        "java/Syntax02MissingParen.java",
        "java/Runtime01OrderPipeline.java",
        "java/Logic01CartReport.java",
    ],
}

FORBIDDEN_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".verify_java_classes"}
FORBIDDEN_SUFFIXES = {".class", ".pyc", ".pyo", ".jar", ".orig", ".rej"}


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #

class Results:
    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose
        self.rows: list[tuple[str, str, str]] = []

    def add(self, status: str, name: str, detail: str = "") -> None:
        self.rows.append((status, name, detail))
        if status == "FAIL" or (status == "SKIP" and self.verbose) or self.verbose:
            line = f"[{status}] {name}"
            if detail:
                line += f" :: {detail}"
            safe_print(line)

    def ok(self, name: str, detail: str = "") -> None:
        self.add("PASS", name, detail)

    def fail(self, name: str, detail: str = "") -> None:
        self.add("FAIL", name, detail)

    def skip(self, name: str, detail: str = "") -> None:
        self.add("SKIP", name, detail)

    def counts(self) -> tuple[int, int, int]:
        passed = sum(1 for s, _, _ in self.rows if s == "PASS")
        failed = sum(1 for s, _, _ in self.rows if s == "FAIL")
        skipped = sum(1 for s, _, _ in self.rows if s == "SKIP")
        return passed, failed, skipped


def safe_print(*parts: object) -> None:
    text = " ".join(str(p) for p in parts)
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        sys.stdout.write(text.encode(enc, "backslashreplace").decode(enc, "replace") + "\n")
    except Exception:
        print(text.encode("ascii", "backslashreplace").decode("ascii"))


def run(cmd: list[str], timeout: int = 90, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd or ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def find_tool(env_var: str, name: str, extra: tuple[str, ...] = ()) -> str | None:
    value = os.environ.get(env_var)
    if value:
        p = Path(value)
        return str(p) if p.is_file() else None
    found = shutil.which(name)
    if found:
        return found
    for candidate in extra:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def find_java_tools() -> tuple[str | None, str | None]:
    javac = find_tool("JAVAC_BIN", "javac")
    java = find_tool("JAVA_BIN", "java")
    home = os.environ.get("JAVA_HOME")
    if home:
        if javac is None and (Path(home) / "bin" / "javac.exe").is_file():
            javac = str(Path(home) / "bin" / "javac.exe")
        if javac is None and (Path(home) / "bin" / "javac").is_file():
            javac = str(Path(home) / "bin" / "javac")
        if java is None and (Path(home) / "bin" / "java.exe").is_file():
            java = str(Path(home) / "bin" / "java.exe")
        if java is None and (Path(home) / "bin" / "java").is_file():
            java = str(Path(home) / "bin" / "java")
    if java is None and javac is not None:
        candidate = Path(javac).with_name("java.exe")
        if candidate.is_file():
            java = str(candidate)
        else:
            candidate = Path(javac).with_name("java")
            if candidate.is_file():
                java = str(candidate)
    return javac, java


def first_non_ascii(text: str) -> tuple[int, int, str] | None:
    for lineno, line in enumerate(text.splitlines(), 1):
        for col, ch in enumerate(line, 1):
            if ord(ch) > 127:
                return lineno, col, ch
    return None


def count_functions(language: str, text: str) -> int:
    if language == "python":
        return len(re.findall(r"(?m)^\s*def\s+[A-Za-z_]\w*\s*\(", text))
    if language == "javascript":
        declarations = re.findall(r"\bfunction\s+[A-Za-z_$][\w$]*\s*\(", text)
        arrows = re.findall(
            r"(?:const|let|var)\s+[A-Za-z_$][\w$]*\s*=\s*(?:async\s*)?"
            r"(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>",
            text,
        )
        return len(declarations) + len(arrows)
    if language == "java":
        pattern = (
            r"(?m)^[ \t]+(?:(?:public|private|protected)\s+)?(?:static\s+)?(?:final\s+)?"
            r"(?:void|[A-Za-z_$][\w$.]*(?:<[^<>{};]*>)?(?:\[\])*)"
            r"\s+[A-Za-z_$][\w$]*\s*\([^;{}]*\)\s*\{"
        )
        return len(re.findall(pattern, text))
    return 0


# --------------------------------------------------------------------------- #
# toolchain availability
# --------------------------------------------------------------------------- #

class Toolchains:
    def __init__(self) -> None:
        self.python = sys.executable
        self.node = find_tool("NODE_BIN", "node")
        self.javac, self.java = find_java_tools()

    def missing_for(self, language: str) -> list[str]:
        missing: list[str] = []
        if language == "python" and not self.python:
            missing.append("python")
        if language == "javascript" and not self.node:
            missing.append("node")
        if language == "java":
            if not self.javac:
                missing.append("javac")
            if not self.java:
                missing.append("java")
        return missing


# --------------------------------------------------------------------------- #
# checks
# --------------------------------------------------------------------------- #

def load_manifest(results: Results) -> dict | None:
    if not MANIFEST_PATH.is_file():
        results.fail("manifest", f"missing {MANIFEST_PATH.name}")
        return None
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - report any JSON problem
        results.fail("manifest", f"invalid JSON: {exc}")
        return None
    if not isinstance(manifest, dict):
        results.fail("manifest", "top-level value must be an object")
        return None
    results.ok("manifest: loaded")
    return manifest


def check_structure(
    manifest: dict, results: Results, languages: list[str]
) -> dict[str, dict]:
    """Validate manifest bookkeeping and source file rules. Returns cases by id."""
    all_languages = set(LANG_PREFIX)
    selected = set(languages)
    expected_ids: set[str] = set()
    for language in languages:
        prefix = LANG_PREFIX[language]
        expected_ids.add(f"{prefix}-syn-01")
        expected_ids.add(f"{prefix}-syn-02")
        expected_ids.update(f"{prefix}-run-R{i}" for i in range(1, 7))
        expected_ids.update(f"{prefix}-logic-L{i}" for i in range(1, 7))

    cases = manifest.get("cases")
    if not isinstance(cases, list):
        results.fail("manifest.cases", "missing or not a list")
        return {}
    by_id: dict[str, dict] = {}
    duplicates: list[str] = []
    for entry in cases:
        if not isinstance(entry, dict) or "id" not in entry:
            results.fail("manifest.cases", f"entry without id: {entry!r:.120}")
            continue
        cid = entry["id"]
        if cid in by_id:
            duplicates.append(cid)
        by_id[cid] = entry
    if duplicates:
        results.fail("manifest.cases", f"duplicate ids: {sorted(set(duplicates))}")

    missing = expected_ids - set(by_id)
    extra = set(by_id) - expected_ids if selected == all_languages else set()
    if missing:
        results.fail("manifest.cases", f"missing ids: {sorted(missing)}")
    if extra:
        results.fail("manifest.cases", f"unexpected ids: {sorted(extra)}")
    if not missing and not extra:
        results.ok(f"manifest: {len(by_id)} case ids match the expected inventory")

    # kind consistency
    for cid, entry in by_id.items():
        parts = cid.split("-")
        language = {"py": "python", "js": "javascript", "java": "java"}.get(parts[0])
        kind = {"syn": "syntax", "run": "runtime", "logic": "logic"}.get(parts[1])
        if entry.get("language") != language:
            results.fail(f"manifest:{cid}", f"language {entry.get('language')!r} != {language!r}")
        if entry.get("kind") != kind:
            results.fail(f"manifest:{cid}", f"kind {entry.get('kind')!r} != {kind!r}")
        path = entry.get("file")
        if not isinstance(path, str) or Path(path).suffix == "":
            results.fail(f"manifest:{cid}", f"bad file field: {path!r}")

    # files
    files = manifest.get("files")
    if not isinstance(files, list):
        results.fail("manifest.files", "missing or not a list")
        files = []
    declared = {}
    for item in files:
        if not isinstance(item, dict) or "path" not in item:
            results.fail("manifest.files", f"bad entry: {item!r:.120}")
            continue
        declared[item["path"]] = item

    expected_files = [
        p for language, paths in EXPECTED_FILES.items() if language in selected for p in paths
    ]
    missing_files = sorted(set(expected_files) - set(declared))
    extra_files = sorted(set(declared) - set(expected_files)) if selected == all_languages else []
    if missing_files or extra_files:
        results.fail(
            "manifest.files",
            f"file inventory mismatch; missing={missing_files} unexpected={extra_files}",
        )
    else:
        results.ok(f"manifest: {len(expected_files)} source files declared")

    # every case must reference a declared file
    for cid, entry in by_id.items():
        if entry.get("file") not in declared:
            results.fail(f"manifest:{cid}", f"file not declared: {entry.get('file')!r}")

    # source files on disk
    for path in expected_files:
        fp = ROOT / path
        language = path.split("/", 1)[0]
        kind = declared.get(path, {}).get("kind", "?")
        if not fp.is_file():
            results.fail(f"file:{path}", "missing on disk")
            continue
        data = fp.read_bytes()
        ok = True
        if data.startswith(b"\xef\xbb\xbf"):
            results.fail(f"file:{path}", "UTF-8 BOM detected (must be BOM-free)")
            ok = False
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            results.fail(f"file:{path}", f"not valid UTF-8: {exc}")
            continue
        bad = first_non_ascii(text)
        if bad:
            results.fail(f"file:{path}", f"non-ASCII character {bad[2]!r} at line {bad[0]} col {bad[1]}")
            ok = False
        lines = len(text.splitlines())
        declared_lines = declared.get(path, {}).get("lines")
        if declared_lines != lines:
            results.fail(
                f"file:{path}",
                f"line count mismatch: manifest says {declared_lines}, disk says {lines}",
            )
            ok = False
        minimum = THRESHOLDS.get(kind, 0)
        if lines < minimum:
            results.fail(f"file:{path}", f"too short: {lines} lines < required {minimum}")
            ok = False
        functions = count_functions(language, text)
        if functions < 10:
            results.fail(f"file:{path}", f"only {functions} functions/methods found (< 10)")
            ok = False
        if ok:
            results.ok(f"file:{path}: {lines} lines, {functions} functions, ASCII clean")

    return by_id


def check_python_syntax(entry: dict, tools: Toolchains, results: Results) -> None:
    cid, fp = entry["id"], ROOT / entry["file"]
    proc = run(
        [
            tools.python,
            "-c",
            "import ast,sys; ast.parse(open(sys.argv[1],encoding='utf-8').read(), filename=sys.argv[1])",
            str(fp),
        ]
    )
    if proc.returncode == 0:
        results.fail(cid, "parser unexpectedly accepted the file")
        return
    stderr = proc.stderr
    lines = [int(n) for n in re.findall(r'line (\d+)', stderr)]
    actual_line = lines[-1] if lines else None
    problems = []
    if actual_line != entry.get("line"):
        problems.append(f"reported line {actual_line} != documented {entry.get('line')}")
    pattern = entry.get("diagnostic_pattern", "")
    if pattern and pattern not in stderr:
        problems.append(f"diagnostic {pattern!r} not in parser output")
    if "SyntaxError" not in stderr and "IndentationError" not in stderr:
        problems.append("no SyntaxError/IndentationError in output")
    if problems:
        results.fail(cid, "; ".join(problems))
    else:
        results.ok(cid, f"{entry.get('error_type')} at line {actual_line}")


def check_javascript_syntax(entry: dict, tools: Toolchains, results: Results) -> None:
    cid, fp = entry["id"], ROOT / entry["file"]
    proc = run([tools.node, "--check", str(fp)])
    if proc.returncode == 0:
        results.fail(cid, "node --check unexpectedly accepted the file")
        return
    stderr = proc.stderr
    matches = re.findall(re.escape(str(fp)) + r":(\d+)(?::\d+)?", stderr)
    actual_line = int(matches[0]) if matches else None
    problems = []
    if actual_line != entry.get("line"):
        problems.append(f"reported line {actual_line} != documented {entry.get('line')}")
    pattern = entry.get("diagnostic_pattern", "")
    if pattern and pattern not in stderr:
        problems.append(f"diagnostic {pattern!r} not in node output")
    if "SyntaxError" not in stderr:
        problems.append("no SyntaxError in node output")
    if problems:
        results.fail(cid, "; ".join(problems))
    else:
        results.ok(cid, f"{entry.get('error_type')} at line {actual_line}")


def check_java_syntax(entry: dict, tools: Toolchains, results: Results, classes_dir: Path) -> None:
    cid, fp = entry["id"], ROOT / entry["file"]
    proc = run(
        [
            tools.javac,
            "-J-Duser.language=en",
            "-J-Duser.country=US",
            "-encoding",
            "UTF-8",
            "-d",
            str(classes_dir),
            str(fp),
        ]
    )
    if proc.returncode == 0:
        results.fail(cid, "javac unexpectedly accepted the file")
        return
    stderr = proc.stderr
    actual_line = None
    match = re.search(re.escape(fp.name) + r":(\d+):\s*error:", stderr)
    if match:
        actual_line = int(match.group(1))
    problems = []
    if actual_line != entry.get("line"):
        problems.append(f"reported line {actual_line} != documented {entry.get('line')}")
    pattern = entry.get("diagnostic_pattern", "")
    if pattern and pattern not in stderr:
        problems.append(f"diagnostic {pattern!r} not in javac output")
    if "error:" not in stderr:
        problems.append("no javac error in output")
    if problems:
        results.fail(cid, "; ".join(problems))
    else:
        results.ok(cid, f"{entry.get('error_type')} at line {actual_line}")


def check_python_runtime(entry: dict, tools: Toolchains, results: Results) -> None:
    cid, fp = entry["id"], ROOT / entry["file"]
    proc = run([tools.python, str(fp), entry["case"]])
    if proc.returncode == 0:
        results.fail(cid, "case exited with code 0 (expected an uncaught exception)")
        return
    stderr = proc.stderr
    frames = [int(n) for n in re.findall(r'File ".*?", line (\d+)', stderr)]
    actual_line = frames[-1] if frames else None
    problems = []
    if actual_line != entry.get("line"):
        problems.append(f"raising line {actual_line} != documented {entry.get('line')}")
    if entry.get("exception") not in stderr:
        problems.append(f"exception {entry.get('exception')!r} not in stderr")
    pattern = entry.get("message_pattern", "")
    if pattern and pattern not in stderr:
        problems.append(f"message {pattern!r} not in stderr")
    if problems:
        results.fail(cid, "; ".join(problems))
    else:
        results.ok(cid, f"{entry.get('exception')} at line {actual_line}")


def check_javascript_runtime(entry: dict, tools: Toolchains, results: Results) -> None:
    cid, fp = entry["id"], ROOT / entry["file"]
    proc = run([tools.node, str(fp), entry["case"]])
    if proc.returncode == 0:
        results.fail(cid, "case exited with code 0 (expected an uncaught exception)")
        return
    stderr = proc.stderr
    matches = re.findall(re.escape(str(fp)) + r":(\d+)(?::\d+)?", stderr)
    actual_line = int(matches[0]) if matches else None
    problems = []
    if actual_line != entry.get("line"):
        problems.append(f"raising line {actual_line} != documented {entry.get('line')}")
    if entry.get("exception") not in stderr:
        problems.append(f"exception {entry.get('exception')!r} not in stderr")
    pattern = entry.get("message_pattern", "")
    if pattern and pattern not in stderr:
        problems.append(f"message {pattern!r} not in stderr")
    if problems:
        results.fail(cid, "; ".join(problems))
    else:
        results.ok(cid, f"{entry.get('exception')} at line {actual_line}")


def check_java_valid_compile(entry: dict, tools: Toolchains, results: Results, classes_dir: Path) -> bool:
    fp = ROOT / entry["file"]
    proc = run(
        [
            tools.javac,
            "-J-Duser.language=en",
            "-J-Duser.country=US",
            "-encoding",
            "UTF-8",
            "-d",
            str(classes_dir),
            str(fp),
        ]
    )
    if proc.returncode != 0:
        results.fail(f"compile:{entry['file']}", f"javac failed: {proc.stderr.strip()[:400]}")
        return False
    return True


def check_java_runtime(entry: dict, tools: Toolchains, results: Results, classes_dir: Path) -> None:
    cid, fp = entry["id"], ROOT / entry["file"]
    stem = fp.stem
    proc = run(
        [
            tools.java,
            "-Duser.language=en",
            "-Duser.country=US",
            "-cp",
            str(classes_dir),
            stem,
            entry["case"],
        ]
    )
    if proc.returncode == 0:
        results.fail(cid, "case exited with code 0 (expected an uncaught exception)")
        return
    stderr = proc.stderr
    frame_match = re.search(r"\(" + re.escape(stem) + r"\.java:(\d+)\)", stderr)
    actual_line = int(frame_match.group(1)) if frame_match else None
    problems = []
    if actual_line != entry.get("line"):
        problems.append(f"raising line {actual_line} != documented {entry.get('line')}")
    if entry.get("exception") not in stderr:
        problems.append(f"exception {entry.get('exception')!r} not in stderr")
    pattern = entry.get("message_pattern", "")
    if pattern and pattern not in stderr:
        problems.append(f"message {pattern!r} not in stderr")
    if problems:
        results.fail(cid, "; ".join(problems))
    else:
        results.ok(cid, f"{entry.get('exception')} at line {actual_line}")


def check_logic(
    entry: dict,
    language: str,
    tools: Toolchains,
    results: Results,
    classes_dir: Path | None,
) -> None:
    cid, fp = entry["id"], ROOT / entry["file"]
    expected, actual = entry.get("expected"), entry.get("actual")
    if not isinstance(expected, str) or not isinstance(actual, str):
        results.fail(cid, "expected/actual must be strings")
        return
    if expected == actual:
        results.fail(cid, "expected value equals actual value (not a bug)")
        return
    if language == "python":
        proc = run([tools.python, str(fp), entry["case"]])
    elif language == "javascript":
        proc = run([tools.node, str(fp), entry["case"]])
    else:
        proc = run(
            [
                tools.java,
                "-Duser.language=en",
                "-Duser.country=US",
                "-cp",
                str(classes_dir),
                fp.stem,
                entry["case"],
            ]
        )
    if proc.returncode != 0:
        results.fail(cid, f"case exited with code {proc.returncode}: {proc.stderr.strip()[:300]}")
        return
    stdout = proc.stdout.strip()
    problems = []
    if stdout != actual:
        problems.append(f"stdout {stdout!r} != documented actual {actual!r}")
    if len(proc.stdout.splitlines()) > 1:
        problems.append(f"expected exactly one stdout line, got {len(proc.stdout.splitlines())}")
    if problems:
        results.fail(cid, "; ".join(problems))
    else:
        results.ok(cid, f"buggy output {stdout!r} != expected {expected!r}")


def check_cli_contract(
    entry_file: str,
    language: str,
    tools: Toolchains,
    results: Results,
    classes_dir: Path | None,
) -> None:
    """No-arg => usage + exit 0; unknown case => exit 2."""
    fp = ROOT / entry_file
    if language == "python":
        base = [tools.python, str(fp)]
    elif language == "javascript":
        base = [tools.node, str(fp)]
    else:
        base = [
            tools.java,
            "-Duser.language=en",
            "-Duser.country=US",
            "-cp",
            str(classes_dir),
            fp.stem,
        ]
    no_arg = run(base)
    if no_arg.returncode != 0:
        results.fail(f"cli:{entry_file}", f"no-arg run exited {no_arg.returncode} (expected 0)")
    elif "usage" not in no_arg.stdout.lower():
        results.fail(f"cli:{entry_file}", "no-arg run did not print a usage line")
    unknown = run(base + ["__NO_SUCH_CASE__"])
    if unknown.returncode != 2:
        results.fail(f"cli:{entry_file}", f"unknown case exited {unknown.returncode} (expected 2)")


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Verify the deliberate-error code corpus.")
    parser.add_argument(
        "--lang",
        action="append",
        choices=sorted(LANG_PREFIX),
        help="only check this language (repeatable; default: all)",
    )
    parser.add_argument("--strict", action="store_true", help="missing toolchain is a failure")
    parser.add_argument("--verbose", action="store_true", help="print every check")
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(errors="backslashreplace")  # type: ignore[attr-defined]
    except Exception:
        pass

    results = Results(verbose=args.verbose)
    tools = Toolchains()
    manifest = load_manifest(results)
    if manifest is None:
        safe_print("RESULT: FAIL (no manifest)")
        return 1

    languages = args.lang or list(LANG_PREFIX)
    cases = check_structure(manifest, results, languages)
    classes_dir_root: Path | None = None
    java_classes: Path | None = None
    try:
        if "java" in languages:
            # NOTE: on some Windows sandboxes javac/java cannot write into a
            # directory created by tempfile.mkdtemp (restrictive ACL).  Use a
            # plain directory under the package root instead and clean it up.
            classes_dir_root = ROOT / ".verify_java_classes"
            if classes_dir_root.exists():
                shutil.rmtree(classes_dir_root, ignore_errors=True)
            classes_dir_root.mkdir()
            java_classes = classes_dir_root

        syntax_checks = {
            "python": check_python_syntax,
            "javascript": check_javascript_syntax,
            "java": lambda e, t, r: check_java_syntax(e, t, r, java_classes),
        }
        runtime_checks = {
            "python": check_python_runtime,
            "javascript": check_javascript_runtime,
            "java": lambda e, t, r: check_java_runtime(e, t, r, java_classes),
        }

        for language in languages:
            label = LANG_LABEL[language]
            missing = tools.missing_for(language)
            if missing:
                msg = f"missing toolchain: {', '.join(missing)}"
                if args.strict:
                    results.fail(f"toolchain:{language}", msg)
                else:
                    results.skip(f"toolchain:{language}", msg + " (use --strict to enforce)")
                    continue

            safe_print(f"\n=== {label} ===")
            lang_cases = [c for c in cases.values() if c.get("language") == language]

            # valid files must parse/compile without intentional syntax errors
            if language == "java":
                compiled_files: set[str] = set()
                for entry in lang_cases:
                    if entry.get("kind") in {"runtime", "logic"} and entry["file"] not in compiled_files:
                        compiled_files.add(entry["file"])
                        check_java_valid_compile(entry, tools, results, java_classes)  # type: ignore[arg-type]
            elif language == "python":
                for path in EXPECTED_FILES["python"]:
                    if "syntax" in Path(path).name:
                        continue
                    proc = run(
                        [
                            tools.python,
                            "-c",
                            "import ast,sys; ast.parse(open(sys.argv[1],encoding='utf-8').read(), filename=sys.argv[1])",
                            str(ROOT / path),
                        ]
                    )
                    if proc.returncode != 0:
                        results.fail(f"parse:{path}", f"unexpected SyntaxError: {proc.stderr.strip()[:300]}")
            else:
                for path in EXPECTED_FILES["javascript"]:
                    if "syntax" in Path(path).name:
                        continue
                    proc = run([tools.node, "--check", str(ROOT / path)])
                    if proc.returncode != 0:
                        results.fail(f"parse:{path}", f"unexpected SyntaxError: {proc.stderr.strip()[:300]}")

            for entry in sorted(lang_cases, key=lambda e: e["id"]):
                kind = entry.get("kind")
                if kind == "syntax":
                    syntax_checks[language](entry, tools, results)
                elif kind == "runtime":
                    runtime_checks[language](entry, tools, results)
                elif kind == "logic":
                    check_logic(entry, language, tools, results, java_classes)
                else:
                    results.fail(entry["id"], f"unknown kind {kind!r}")

            # CLI contract is checked once per runtime/logic file
            checked_files: set[str] = set()
            for entry in lang_cases:
                if entry.get("kind") in {"runtime", "logic"} and entry["file"] not in checked_files:
                    checked_files.add(entry["file"])
                    check_cli_contract(entry["file"], language, tools, results, java_classes)
    finally:
        if classes_dir_root is not None:
            shutil.rmtree(classes_dir_root, ignore_errors=True)

    # forbidden artifacts left in the corpus
    for path in ROOT.rglob("*"):
        if path.is_dir() and path.name in FORBIDDEN_DIRS:
            results.fail("artifacts", f"forbidden directory present: {path.relative_to(ROOT)}")
        elif path.is_file() and path.suffix.lower() in FORBIDDEN_SUFFIXES:
            results.fail("artifacts", f"forbidden build artifact present: {path.relative_to(ROOT)}")

    passed, failed, skipped = results.counts()
    safe_print("")
    safe_print(f"Summary: {passed} passed, {failed} failed, {skipped} skipped")
    safe_print("RESULT: " + ("PASS" if failed == 0 else "FAIL"))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

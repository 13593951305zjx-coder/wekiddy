Code Review Test Samples
========================

Upload one .py file at a time in the Code Review website and click static analysis.

01_command_injection.py       PY-CMD-001, PY-CMD-002
02_hardcoded_secrets.py       PY-SECRET-001 (3 findings)
03_unsafe_deserialization.py  PY-DESERIALIZE-001, PY-DESERIALIZE-002
04_dynamic_sql.py             PY-SQL-001
05_disabled_tls.py             PY-TLS-001 (2 findings)
06_dynamic_execution.py       PY-EVAL-001
07_syntax_error.py             PY-SYNTAX

These files are intentionally unsafe test samples. Do not use them in a real project.

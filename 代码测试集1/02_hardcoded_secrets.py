# Expected: PY-SECRET-001 findings

API_KEY = "sk-demo-1234567890"
database_password = "admin123"
access_token = "token-for-local-test-only"


def connect() -> str:
    return f"{API_KEY}:{database_password}:{access_token}"


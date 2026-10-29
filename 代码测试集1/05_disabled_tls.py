import requests


def fetch_remote_data(url: str):
    # Expected: PY-TLS-001 findings
    first = requests.get(url, verify=False, timeout=5)
    session = requests.Session()
    second = session.post(url, verify=False, timeout=5)
    return first.text, second.text

